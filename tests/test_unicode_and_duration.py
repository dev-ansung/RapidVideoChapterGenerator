import json
import subprocess
import threading
import unicodedata
import urllib.request
from pathlib import Path
from typing import TypeAlias
from unittest.mock import patch

import pytest

from rvcg.models import BoundaryConfig
from rvcg.probe import parse_duration_tag, probe_duration, probe_embedded_chapters
from rvcg.scanner import parse_ffmpeg_line
from rvcg.server import create_lifecycle_server, resolve_any_path

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def test_parse_duration_tag_formats() -> None:
    assert parse_duration_tag("01:02:03.500000000") == 3723.5
    assert parse_duration_tag("N/A") is None
    assert parse_duration_tag("") is None


def test_probe_duration_handles_na_format_duration(tmp_path: Path) -> None:
    fake_vid = tmp_path / "na_video.mkv"
    fake_vid.write_bytes(b"00")

    mock_json = json.dumps(
        {
            "streams": [{"duration": "N/A", "tags": {"DURATION": "00:05:12.500000000"}}],
            "format": {"duration": "N/A"},
        }
    )
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=mock_json, stderr=""),
    ):
        assert probe_duration(fake_vid) == 312.5


def test_probe_duration_raises_clean_error_when_all_na(tmp_path: Path) -> None:
    fake_vid = tmp_path / "corrupt.mp4"
    fake_vid.write_bytes(b"00")

    with patch(
        "subprocess.run",
        side_effect=[
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"format": {"duration": "N/A"}, "streams": []}), stderr=""
            ),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="N/A\n", stderr=""),
        ],
    ):
        with pytest.raises(RuntimeError, match="Cannot determine duration"):
            probe_duration(fake_vid)


def test_probe_embedded_chapters_ignores_na_timestamps(tmp_path: Path) -> None:
    fake_vid = tmp_path / "ch.mp4"
    fake_vid.write_bytes(b"00")

    mock_json = json.dumps(
        {
            "chapters": [
                {"start_time": "N/A", "end_time": "100.0", "tags": {"title": "Bad"}},
                {"start_time": "0.0", "end_time": "120.0", "tags": {"title": "【序章】温泉旅行 • 第1話"}},
            ]
        }
    )
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=mock_json, stderr=""),
    ):
        ch = probe_embedded_chapters(fake_vid, min_chapter_sec=10.0)
        assert len(ch) == 1
        assert ch[0][2] == "【序章】温泉旅行 • 第1話"


def test_parse_ffmpeg_line_ignores_na_values() -> None:
    ev = parse_ffmpeg_line(
        "frame:1 pts:N/A pts_time:N/A lavfi.scene_score=N/A out_time_us=N/A",
        t_start=0.0,
        chunk_dur=100.0,
        cur_local_t=None,
    )
    assert ev.new_local_t is None
    assert ev.progress_sec is None
    assert ev.visual_cuts == []


def test_unicode_filename_and_nfd_nfc_resolution_and_scan(tmp_path: Path) -> None:
    raw_name = "STARS-172•【無修正流出】從順溫泉旅行 がぎぐ #1 (テスト).mp4"
    nfd_name = unicodedata.normalize("NFD", raw_name)
    nfc_name = unicodedata.normalize("NFC", raw_name)

    vid_path = tmp_path / nfd_name
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
            str(vid_path),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
    )

    resolved_nfc, kind = resolve_any_path(str(tmp_path / nfc_name))
    assert kind == "file"
    assert resolved_nfc is not None and resolved_nfc.exists()

    server = create_lifecycle_server(default_dir=tmp_path, default_config=BoundaryConfig())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    base_url = f"http://{host}:{port}"

    try:
        scan_req = urllib.request.Request(
            f"{base_url}/api/scan",
            data=json.dumps(
                {
                    "path": str(vid_path),
                    "refresh": True,
                    "min_seg": 1.0,
                    "max_seg": 2.0,
                    "target_seg": 2.0,
                    "threshold": 0.38,
                    "workers": 2,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(scan_req, timeout=15) as resp:
            start_data: dict[str, JsonValue] = json.loads(resp.read().decode("utf-8"))
        job_id = str(start_data["job_id"])

        complete_event: dict[str, JsonValue] | None = None
        with urllib.request.urlopen(f"{base_url}/api/jobs/{job_id}/events", timeout=15) as sse_resp:
            for raw_line in sse_resp:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("data: "):
                    ev: dict[str, JsonValue] = json.loads(line[6:])
                    if ev.get("type") == "complete":
                        complete_event = ev
                        break
                    if ev.get("type") == "error":
                        pytest.fail(f"Scan failed with error: {ev.get('error')}")

        assert complete_event is not None

        save_req = urllib.request.Request(
            f"{base_url}/api/chapters/save",
            data=json.dumps(
                {
                    "path": str(vid_path),
                    "chapters": [
                        {"start_time": 0.0, "end_time": 2.0, "title": "第一幕：溫泉旅行 • 始まり"},
                        {"start_time": 2.0, "end_time": 4.0, "title": "第二幕：終章 【完】"},
                    ],
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(save_req, timeout=15) as save_resp:
            save_data: dict[str, JsonValue] = json.loads(save_resp.read().decode("utf-8"))
        assert save_data.get("ok") is True

        chapters = probe_embedded_chapters(vid_path, min_chapter_sec=0.5)
        assert len(chapters) == 2
        assert chapters[0][2] == "第一幕：溫泉旅行 • 始まり"
        assert chapters[1][2] == "第二幕：終章 【完】"
    finally:
        server.shutdown()
        server.server_close()
