import json
import subprocess
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TypeAlias

from rvcg.models import BoundaryConfig
from rvcg.probe import probe_embedded_chapters
from rvcg.server import create_lifecycle_server

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _make_sample_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:d=4",
            "-c:v",
            "libx264",
            "-g",
            "15",
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
    )


def _post_json(url: str, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        res: dict[str, JsonValue] = json.loads(resp.read().decode("utf-8"))
        return res


def _get_json(url: str) -> dict[str, JsonValue]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        res: dict[str, JsonValue] = json.loads(resp.read().decode("utf-8"))
        return res


def test_lifecycle_server_endpoints(tmp_path: Path) -> None:
    vid = tmp_path / "demo clip.mp4"
    _make_sample_video(vid)

    server = create_lifecycle_server(default_dir=tmp_path, default_config=BoundaryConfig())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    base_url = f"http://{host}:{port}"

    try:
        with urllib.request.urlopen(f"{base_url}/", timeout=5) as root_resp:
            html = root_resp.read().decode("utf-8")
            assert "RapidVideoChapterGenerator" in html

        fs_data = _get_json(f"{base_url}/api/fs")
        videos = fs_data.get("videos")
        assert isinstance(videos, list)
        assert len(videos) == 1

        escaped = str(vid).replace(" ", r"\ ")
        resolved = _post_json(f"{base_url}/api/resolve-path", {"path": escaped})
        assert resolved.get("ok") is True
        assert resolved.get("path") == str(vid.resolve())

        req_range = urllib.request.Request(
            f"{base_url}/api/media?path={urllib.parse.quote(str(vid))}",
            headers={"Range": "bytes=0-15"},
        )
        with urllib.request.urlopen(req_range, timeout=5) as range_resp:
            assert range_resp.status == 206
            chunk = range_resp.read()
            assert len(chunk) == 16

        recalc = _post_json(
            f"{base_url}/api/chapters/recalc",
            {
                "chapters": [
                    {"start_time": 0.0, "end_time": 2.0, "title": "Opening"},
                    {"start_time": 2.0, "end_time": 4.0, "title": "Finale"},
                ]
            },
        )
        recalc_list = recalc.get("chapters")
        assert isinstance(recalc_list, list)
        assert len(recalc_list) == 2

        saved = _post_json(
            f"{base_url}/api/chapters/save",
            {
                "path": str(vid),
                "chapters": [
                    {"start_time": 0.0, "end_time": 2.0, "title": "Opening"},
                    {"start_time": 2.0, "end_time": 4.0, "title": "Finale"},
                ],
            },
        )
        assert saved.get("ok") is True
        embedded = probe_embedded_chapters(vid, min_chapter_sec=0.5)
        assert len(embedded) == 2
        assert embedded[0][2] == "Opening"

        exported = _post_json(
            f"{base_url}/api/chapters/export",
            {
                "format": "youtube",
                "chapters": [
                    {"start_time": 0.0, "end_time": 2.0, "title": "Opening"},
                    {"start_time": 2.0, "end_time": 4.0, "title": "Finale"},
                ],
            },
        )
        assert "00:00:00 - Opening" in str(exported.get("content", ""))

        scan_start = _post_json(
            f"{base_url}/api/scan",
            {
                "path": str(vid),
                "refresh": True,
                "min_seg": 1.0,
                "max_seg": 2.0,
                "target_seg": 2.0,
                "threshold": 0.38,
                "workers": 2,
            },
        )
        job_id = str(scan_start["job_id"])
        events: list[dict[str, JsonValue]] = []
        with urllib.request.urlopen(f"{base_url}/api/jobs/{job_id}/events", timeout=15) as sse_resp:
            for raw_line in sse_resp:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("data: "):
                    ev: dict[str, JsonValue] = json.loads(line[6:])
                    events.append(ev)
                    if ev.get("type") in {"complete", "error"}:
                        break
        assert any(e.get("type") == "complete" for e in events)
    finally:
        server.shutdown()
        server.server_close()
