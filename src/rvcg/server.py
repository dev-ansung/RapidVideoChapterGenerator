import hashlib
import json
import mimetypes
import queue
import re
import shlex
import tempfile
import threading
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rvcg.models import BoundaryConfig, SceneSegment, SpriteMeta
from rvcg.muxer import embed_chapters_atomic, format_chapters_export
from rvcg.probe import extract_subtitles, probe_duration, probe_embedded_chapters
from rvcg.scanner import scan_keyframes
from rvcg.solver import compute_cell_times, segments_from_tuples, solve_boundaries
from rvcg.webui import render_webui_html

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".m4v", ".webm"}


@dataclass
class ScanJob:
    job_id: str
    video_path: Path
    events: queue.Queue[str | None] = field(default_factory=queue.Queue)


def resolve_any_path(raw: str) -> tuple[Path | None, str]:
    s = raw.strip()
    if not s:
        return None, "missing"
    try:
        parts = shlex.split(s)
        cleaned = parts[0] if parts else s
    except ValueError:
        cleaned = re.sub(r"\\(.)", r"\1", s.strip("'\""))
    p = Path(cleaned).expanduser().resolve()
    if p.is_file():
        return p, "file"
    if p.is_dir():
        return p, "dir"
    return None, "missing"


def parse_chapters_payload(raw_list: list[dict[str, str | int | float]], card_dur: float = 8.4) -> list[SceneSegment]:
    segments: list[SceneSegment] = []
    for idx, item in enumerate(raw_list, 1):
        s = float(item.get("start_time", 0.0))
        e = float(item.get("end_time", s + 1.0))
        title = str(item.get("title", f"Scene {idx:02d}")).strip() or f"Scene {idx:02d}"
        segments.append(
            SceneSegment(
                index=idx,
                start_time=round(s, 2),
                end_time=round(e, 2),
                title=title,
                cell_times=compute_cell_times(s, e, card_dur),
                card_dur=card_dur,
            )
        )
    return segments


class LifecycleServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        default_dir: Path,
        default_config: BoundaryConfig,
        initial_video: Path | None = None,
    ) -> None:
        super().__init__(server_address, LifecycleRequestHandler)
        self.default_dir = default_dir.resolve()
        self.default_config = default_config
        self.initial_video = initial_video.resolve() if initial_video is not None else None
        self.jobs: dict[str, ScanJob] = {}
        self.jobs_lock = threading.Lock()


class LifecycleRequestHandler(BaseHTTPRequestHandler):
    server: LifecycleServer

    def log_message(self, format: str, *args: str | int) -> None:
        return

    def _send_json(self, status: int, payload: str) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body_text(self) -> str:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return "{}"
        return self.rfile.read(length).decode("utf-8")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if route == "/":
            init_vid = str(self.server.initial_video) if self.server.initial_video is not None else None
            html = render_webui_html(str(self.server.default_dir), self.server.default_config, init_vid)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if route == "/api/fs":
            raw_dir = qs.get("dir", [str(self.server.default_dir)])[0]
            target_dir = Path(raw_dir).expanduser().resolve()
            if qs.get("parent", ["0"])[0] == "1":
                target_dir = target_dir.parent
            if not target_dir.is_dir():
                target_dir = self.server.default_dir

            dirs = sorted(
                (
                    {"name": p.name, "path": str(p.resolve())}
                    for p in target_dir.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                ),
                key=lambda x: x["name"].lower(),
            )
            videos = sorted(
                (p for p in target_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            vid_items = [
                {
                    "name": v.name,
                    "path": str(v.resolve()),
                    "size_mb": round(v.stat().st_size / (1024 * 1024), 1),
                }
                for v in videos
            ]
            self._send_json(200, json.dumps({"ok": True, "dir": str(target_dir), "dirs": dirs, "videos": vid_items}))
            return

        if route == "/api/media":
            raw_path = qs.get("path", [""])[0]
            file_path = Path(raw_path).expanduser().resolve()
            if not file_path.is_file():
                self.send_error(404, "File not found")
                return
            self._serve_file_range(file_path)
            return

        if route.startswith("/api/jobs/") and route.endswith("/events"):
            job_id = route.split("/")[3]
            with self.server.jobs_lock:
                job = self.server.jobs.get(job_id)
            if job is None:
                self.send_error(404, "Job not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            while True:
                msg = job.events.get()
                if msg is None:
                    break
                try:
                    self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except BrokenPipeError:
                    break
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        raw_text = self._read_body_text()
        payload = json.loads(raw_text)

        if route == "/api/resolve-path":
            raw_p = str(payload.get("path", ""))
            resolved, kind = resolve_any_path(raw_p)
            if resolved is None:
                self._send_json(200, json.dumps({"ok": False, "kind": "missing"}))
            else:
                self._send_json(200, json.dumps({"ok": True, "path": str(resolved), "kind": kind}))
            return

        if route == "/api/chapters/recalc":
            raw_ch = payload.get("chapters", [])
            segments = parse_chapters_payload(raw_ch, self.server.default_config.card_dur)
            self._send_json(200, json.dumps({"ok": True, "chapters": [s.to_dict() for s in segments]}))
            return

        if route == "/api/chapters/save":
            vid_path = Path(str(payload.get("path", ""))).expanduser().resolve()
            raw_ch = payload.get("chapters", [])
            if not vid_path.is_file():
                self._send_json(400, json.dumps({"ok": False, "error": "Video file not found"}))
                return
            segments = parse_chapters_payload(raw_ch, self.server.default_config.card_dur)
            dest = embed_chapters_atomic(vid_path, segments, output_path=None)
            self._send_json(200, json.dumps({"ok": True, "path": str(dest)}))
            return

        if route == "/api/chapters/export":
            fmt = str(payload.get("format", "youtube"))
            raw_ch = payload.get("chapters", [])
            segments = parse_chapters_payload(raw_ch, self.server.default_config.card_dur)
            content = format_chapters_export(segments, fmt)
            self._send_json(200, json.dumps({"ok": True, "content": content}))
            return

        if route == "/api/scan":
            vid_path = Path(str(payload.get("path", ""))).expanduser().resolve()
            if not vid_path.is_file():
                self._send_json(400, json.dumps({"ok": False, "error": "Video file not found"}))
                return
            refresh = bool(payload.get("refresh", False))
            cfg = BoundaryConfig(
                min_seg=float(payload.get("min_seg", self.server.default_config.min_seg)),
                max_seg=float(payload.get("max_seg", self.server.default_config.max_seg)),
                target_seg=float(payload.get("target_seg", self.server.default_config.target_seg)),
                workers=max(1, int(payload.get("workers", self.server.default_config.workers))),
                scene_threshold=float(payload.get("threshold", self.server.default_config.scene_threshold)),
            )
            job_id = uuid.uuid4().hex[:12]
            job = ScanJob(job_id=job_id, video_path=vid_path)
            with self.server.jobs_lock:
                self.server.jobs[job_id] = job
            t = threading.Thread(target=self._run_scan_job, args=(job, cfg, refresh), daemon=True)
            t.start()
            self._send_json(200, json.dumps({"ok": True, "job_id": job_id}))
            return

        self.send_error(404, "Not found")

    def _run_scan_job(self, job: ScanJob, cfg: BoundaryConfig, refresh: bool) -> None:
        def push_event(ev_payload: str) -> None:
            job.events.put(ev_payload)

        try:
            video_path = job.video_path
            duration = probe_duration(video_path)
            stat = video_path.stat()
            digest = hashlib.sha1(f"{video_path}:{stat.st_size}".encode()).hexdigest()[:10]
            browser_dir = Path(tempfile.gettempdir()) / f"browse_video_{video_path.stem}_{digest}"
            browser_dir.mkdir(parents=True, exist_ok=True)

            def on_phase(phase: int, completed: float, total: float, info: str) -> None:
                push_event(
                    json.dumps(
                        {
                            "type": "phase",
                            "phase": phase,
                            "completed": completed,
                            "total": total,
                            "info": info,
                        }
                    )
                )

            def on_sprite(completed: float) -> None:
                push_event(
                    json.dumps(
                        {
                            "type": "sprite",
                            "completed": completed,
                            "total": duration,
                            "info": "rendering sprite sheet...",
                        }
                    )
                )

            existing = [] if refresh else probe_embedded_chapters(video_path, min_chapter_sec=1.0)
            use_existing = len(existing) >= 2
            if use_existing:
                on_phase(1, 1.0, 1.0, f"{len(existing)} embedded chapters found")
                on_phase(2, duration, duration, "skipped (chapters found)")
                on_phase(3, 1.0, 1.0, "skipped (chapters found)")
                on_phase(4, 1.0, 1.0, "skipped (chapters found)")
                segments = segments_from_tuples(existing, cfg.card_dur)
                on_phase(5, 1.0, 1.0, f"{len(segments)} chapters ready")
            else:
                on_phase(1, 1.0, 1.0, f"0 chapters ({cfg.workers}-worker keyframe scan)")
                on_phase(2, 0.0, duration, "0 black fades · 0 visual cuts")
                segments = []

            with ThreadPoolExecutor(max_workers=2) as ex:
                scan_fut = ex.submit(
                    scan_keyframes,
                    video_path,
                    duration,
                    cfg,
                    browser_dir,
                    True,
                    use_existing,
                    on_phase,
                    on_sprite,
                )
                sub_fut = ex.submit(extract_subtitles, video_path, browser_dir)
                raw_scan, sprite_meta = scan_fut.result()
                sub_tracks = sub_fut.result()

            if not use_existing:
                segments = solve_boundaries(duration, raw_scan, cfg, on_phase)
                on_phase(5, 0.5, 1.0, f"muxing {len(segments)} chapters (-c copy)...")
                embed_chapters_atomic(video_path, segments, output_path=None)
                on_phase(5, 1.0, 1.0, f"{len(segments)} chapters embedded")

            assert sprite_meta is not None
            sprite_abs = browser_dir / sprite_meta.url
            sprite_payload = SpriteMeta(
                url=f"/api/media?path={urllib.parse.quote(str(sprite_abs))}",
                interval=sprite_meta.interval,
                cols=sprite_meta.cols,
                rows=sprite_meta.rows,
                total_frames=sprite_meta.total_frames,
            )
            push_event(
                json.dumps(
                    {
                        "type": "complete",
                        "video_path": str(video_path),
                        "video_name": video_path.name,
                        "sprite": sprite_payload.to_dict(),
                        "chapters": [s.to_dict() for s in segments],
                        "subtitles": [t.to_dict() for t in sub_tracks],
                    }
                )
            )
        except Exception as exc:
            push_event(json.dumps({"type": "error", "error": str(exc)}))
        finally:
            job.events.put(None)

    def _serve_file_range(self, file_path: Path) -> None:
        file_size = file_path.stat().st_size
        ctype, _ = mimetypes.guess_type(str(file_path))
        content_type = ctype or "application/octet-stream"
        range_header = self.headers.get("Range")

        start = 0
        end = file_size - 1
        status = 200

        if range_header and range_header.startswith("bytes="):
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if m:
                s_str, e_str = m.group(1), m.group(2)
                if s_str:
                    start = int(s_str)
                if e_str:
                    end = min(file_size - 1, int(e_str))
                status = 206

        if start >= file_size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()

        with file_path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)


def create_lifecycle_server(
    default_dir: Path,
    default_config: BoundaryConfig,
    initial_video: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
) -> LifecycleServer:
    return LifecycleServer(
        (host, port), default_dir=default_dir, default_config=default_config, initial_video=initial_video
    )
