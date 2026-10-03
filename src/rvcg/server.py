import hashlib
import json
import mimetypes
import queue
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rvcg.models import BoundaryConfig, BoundaryStats, SceneSegment, SpriteMeta, fmt_hms
from rvcg.muxer import embed_chapters_atomic, export_scene_cut, format_chapters_export
from rvcg.probe import extract_subtitles, probe_duration, probe_embedded_chapters, safe_float
from rvcg.scanner import scan_keyframes
from rvcg.solver import compute_cell_times, segments_from_tuples, solve_boundaries_with_stats
from rvcg.webui import STATIC_DIR, render_webui_html

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".m4v", ".webm"}


@dataclass
class ScanJob:
    job_id: str
    video_path: Path
    events: queue.Queue[str | None] = field(default_factory=queue.Queue)


def match_unicode_path(candidate: Path) -> Path | None:
    if candidate.exists():
        return candidate.resolve()
    for form in ("NFC", "NFD"):
        norm_p = Path(unicodedata.normalize(form, str(candidate)))
        if norm_p.exists():
            return norm_p.resolve()
    parent = candidate.parent
    if parent.is_dir():
        target_nfc = unicodedata.normalize("NFC", candidate.name)
        for child in parent.iterdir():
            if unicodedata.normalize("NFC", child.name) == target_nfc:
                return child.resolve()
    return None


def resolve_any_path(raw: str) -> tuple[Path | None, str]:
    s = raw.strip()
    if not s:
        return None, "missing"
    direct = match_unicode_path(Path(s).expanduser())
    if direct is not None:
        return direct, ("file" if direct.is_file() else "dir")
    try:
        parts = shlex.split(s)
        cleaned = parts[0] if parts else s
    except ValueError:
        cleaned = re.sub(r"\\(.)", r"\1", s.strip("'\""))
    resolved = match_unicode_path(Path(cleaned).expanduser())
    if resolved is not None:
        return resolved, ("file" if resolved.is_file() else "dir")
    return None, "missing"


def reveal_in_file_manager(target_path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(target_path)], stdin=subprocess.DEVNULL, check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{target_path}"], stdin=subprocess.DEVNULL, check=False)
    else:
        folder = target_path.parent if target_path.is_file() else target_path
        subprocess.run(["xdg-open", str(folder)], stdin=subprocess.DEVNULL, check=False)


def parse_chapters_payload(raw_list: list[dict[str, str | int | float]], card_dur: float = 8.4) -> list[SceneSegment]:
    segments: list[SceneSegment] = []
    for idx, item in enumerate(raw_list, 1):
        s = safe_float(item.get("start_time")) or 0.0
        e = safe_float(item.get("end_time")) or (s + 1.0)
        raw_title = str(item.get("title", f"Scene {idx:02d}")).strip()
        title = unicodedata.normalize("NFC", raw_title) if raw_title else f"Scene {idx:02d}"
        default_kind = "start" if idx == 1 else "manual"
        default_detail = f"Video start ({fmt_hms(s)})" if idx == 1 else f"Manual cut @ {fmt_hms(s)}"
        cut_kind = str(item.get("cut_kind", default_kind)).strip() or default_kind
        cut_detail = str(item.get("cut_detail", default_detail)).strip() or default_detail
        segments.append(
            SceneSegment(
                index=idx,
                start_time=round(s, 2),
                end_time=round(e, 2),
                title=title,
                cell_times=compute_cell_times(s, e, card_dur),
                card_dur=card_dur,
                cut_kind=cut_kind,
                cut_detail=cut_detail,
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
        return self.rfile.read(length).decode("utf-8", errors="replace")

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

        if route.startswith("/static/"):
            rel_part = urllib.parse.unquote(route[len("/static/") :])
            static_root = STATIC_DIR.resolve()
            candidate = (static_root / rel_part).resolve()
            if not candidate.is_relative_to(static_root) or not candidate.is_file():
                self.send_error(404, "Static asset not found")
                return
            data = candidate.read_bytes()
            ext = candidate.suffix.lower()
            if ext == ".js":
                ctype = "text/javascript; charset=utf-8"
            elif ext == ".css":
                ctype = "text/css; charset=utf-8"
            else:
                guessed, _ = mimetypes.guess_type(str(candidate))
                ctype = guessed or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if route == "/api/fs":
            raw_dir = urllib.parse.unquote(qs.get("dir", [str(self.server.default_dir)])[0])
            matched_dir = match_unicode_path(Path(raw_dir).expanduser())
            target_dir = matched_dir if (matched_dir is not None and matched_dir.is_dir()) else self.server.default_dir
            if qs.get("parent", ["0"])[0] == "1":
                target_dir = target_dir.parent

            dirs = sorted(
                (
                    {"name": unicodedata.normalize("NFC", p.name), "path": str(p.resolve())}
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
                    "name": unicodedata.normalize("NFC", v.name),
                    "path": str(v.resolve()),
                    "size_mb": round(v.stat().st_size / (1024 * 1024), 1),
                }
                for v in videos
            ]
            self._send_json(
                200,
                json.dumps(
                    {"ok": True, "dir": str(target_dir), "dirs": dirs, "videos": vid_items},
                    ensure_ascii=False,
                ),
            )
            return

        if route == "/api/media":
            raw_path = urllib.parse.unquote(qs.get("path", [""])[0])
            file_path = match_unicode_path(Path(raw_path).expanduser())
            if file_path is None or not file_path.is_file():
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
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
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
                except (BrokenPipeError, ConnectionResetError):
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
                self._send_json(200, json.dumps({"ok": False, "kind": "missing"}, ensure_ascii=False))
            else:
                parent_dir = str(resolved.parent if kind == "file" else resolved)
                self._send_json(
                    200,
                    json.dumps(
                        {"ok": True, "path": str(resolved), "kind": kind, "parent_dir": parent_dir},
                        ensure_ascii=False,
                    ),
                )
            return

        if route == "/api/fs/reveal":
            raw_p = str(payload.get("path", ""))
            resolved, _ = resolve_any_path(raw_p)
            if resolved is None:
                self._send_json(404, json.dumps({"ok": False, "error": "Path not found"}, ensure_ascii=False))
                return
            reveal_in_file_manager(resolved)
            self._send_json(200, json.dumps({"ok": True, "path": str(resolved)}, ensure_ascii=False))
            return

        if route == "/api/chapters/recalc":
            raw_ch = payload.get("chapters", [])
            segments = parse_chapters_payload(raw_ch, self.server.default_config.card_dur)
            self._send_json(
                200,
                json.dumps({"ok": True, "chapters": [s.to_dict() for s in segments]}, ensure_ascii=False),
            )
            return

        if route == "/api/chapters/save":
            vid_path, kind = resolve_any_path(str(payload.get("path", "")))
            raw_ch = payload.get("chapters", [])
            if vid_path is None or kind != "file":
                self._send_json(400, json.dumps({"ok": False, "error": "Video file not found"}, ensure_ascii=False))
                return
            segments = parse_chapters_payload(raw_ch, self.server.default_config.card_dur)
            dest = embed_chapters_atomic(vid_path, segments, output_path=None)
            self._send_json(200, json.dumps({"ok": True, "path": str(dest)}, ensure_ascii=False))
            return

        if route == "/api/chapters/export":
            fmt = str(payload.get("format", "youtube"))
            raw_ch = payload.get("chapters", [])
            segments = parse_chapters_payload(raw_ch, self.server.default_config.card_dur)
            content = format_chapters_export(segments, fmt)
            self._send_json(200, json.dumps({"ok": True, "content": content}, ensure_ascii=False))
            return

        if route == "/api/chapters/export-scene":
            vid_path, kind = resolve_any_path(str(payload.get("path", "")))
            raw_scene = payload.get("scene")
            if vid_path is None or kind != "file" or not isinstance(raw_scene, dict):
                self._send_json(400, json.dumps({"ok": False, "error": "Invalid video or scene"}, ensure_ascii=False))
                return
            s_t = safe_float(raw_scene.get("start_time")) or 0.0
            e_t = safe_float(raw_scene.get("end_time")) or (s_t + 1.0)
            idx_num = int(safe_float(raw_scene.get("scene_number") or raw_scene.get("index")) or 1)
            c_dur = safe_float(raw_scene.get("card_dur")) or self.server.default_config.card_dur
            raw_title = str(raw_scene.get("title", f"Scene {idx_num:02d}")).strip()
            title = unicodedata.normalize("NFC", raw_title) if raw_title else f"Scene {idx_num:02d}"
            raw_cells = raw_scene.get("cell_times")
            if isinstance(raw_cells, list) and len(raw_cells) == 8:
                cells = [round(safe_float(x) or s_t, 2) for x in raw_cells]
            else:
                cells = compute_cell_times(s_t, e_t, c_dur)
            seg = SceneSegment(
                index=idx_num,
                start_time=round(s_t, 2),
                end_time=round(e_t, 2),
                title=title,
                cell_times=cells,
                card_dur=c_dur,
            )
            raw_out = str(payload.get("output_path", "")).strip()
            out_target: Path | None = None
            if raw_out:
                cand = Path(raw_out).expanduser()
                if cand.is_dir() or raw_out.endswith("/"):
                    slug = f"{int(s_t) // 3600:02d}-{(int(s_t) % 3600) // 60:02d}-{int(s_t) % 60:02d}"
                    out_target = (cand / f"cut_{seg.id_str}_{slug}.mp4").resolve()
                else:
                    out_target = (cand if cand.suffix else cand.with_suffix(".mp4")).resolve()
            include_intro = bool(payload.get("include_intro", True))
            try:
                out_file = export_scene_cut(vid_path, seg, output_path=out_target, include_intro=include_intro)
                self._send_json(
                    200,
                    json.dumps(
                        {"ok": True, "path": str(out_file), "filename": out_file.name},
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                self._send_json(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return

        if route == "/api/scan":
            vid_path, kind = resolve_any_path(str(payload.get("path", "")))
            if vid_path is None or kind != "file":
                self._send_json(400, json.dumps({"ok": False, "error": "Video file not found"}, ensure_ascii=False))
                return
            refresh = bool(payload.get("refresh", False))
            cfg = BoundaryConfig(
                min_seg=safe_float(payload.get("min_seg")) or self.server.default_config.min_seg,
                max_seg=safe_float(payload.get("max_seg")) or self.server.default_config.max_seg,
                target_seg=safe_float(payload.get("target_seg")) or self.server.default_config.target_seg,
                workers=max(1, int(safe_float(payload.get("workers")) or self.server.default_config.workers)),
                scene_threshold=safe_float(payload.get("threshold")) or self.server.default_config.scene_threshold,
                black_min_dur=safe_float(payload.get("black_min_dur")) or self.server.default_config.black_min_dur,
                enable_black_fades=bool(
                    payload.get("enable_black_fades", self.server.default_config.enable_black_fades)
                ),
                enable_visual_cuts=bool(
                    payload.get("enable_visual_cuts", self.server.default_config.enable_visual_cuts)
                ),
                enable_subdivide=bool(payload.get("enable_subdivide", self.server.default_config.enable_subdivide)),
            )
            job_id = uuid.uuid4().hex[:12]
            job = ScanJob(job_id=job_id, video_path=vid_path)
            with self.server.jobs_lock:
                self.server.jobs[job_id] = job
            t = threading.Thread(target=self._run_scan_job, args=(job, cfg, refresh), daemon=True)
            t.start()
            self._send_json(200, json.dumps({"ok": True, "job_id": job_id}, ensure_ascii=False))
            return

        self.send_error(404, "Not found")

    def _run_scan_job(self, job: ScanJob, cfg: BoundaryConfig, refresh: bool) -> None:
        def push_event(ev_payload: str) -> None:
            job.events.put(ev_payload)

        try:
            video_path = job.video_path
            duration = probe_duration(video_path)
            stat = video_path.stat()
            digest = hashlib.sha1(f"{video_path}:{stat.st_size}".encode("utf-8")).hexdigest()[:12]
            browser_dir = Path(tempfile.gettempdir()) / f"rvcg_browser_{digest}"
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
                        },
                        ensure_ascii=False,
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
                        },
                        ensure_ascii=False,
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
                    False,
                    None if use_existing else on_phase,
                    on_sprite,
                )
                sub_fut = ex.submit(extract_subtitles, video_path, browser_dir)
                raw_scan, sprite_meta = scan_fut.result()
                sub_tracks = sub_fut.result()

            if use_existing:
                stats = BoundaryStats(
                    raw_black=len(raw_scan.black_points),
                    raw_visual=len(raw_scan.visual_cuts),
                    logs=[
                        f"[Embedded] Loaded {len(segments)} existing chapters from container metadata",
                        *[f"[Result] #{s.id_str} {s.title}: {s.source_range} ({s.duration_str})" for s in segments],
                    ],
                )
            else:
                segments, stats = solve_boundaries_with_stats(duration, raw_scan, cfg, on_phase)
                on_phase(5, 1.0, 1.0, f"{len(segments)} chapters ready")

            assert sprite_meta is not None
            sprite_abs = browser_dir / sprite_meta.url
            sprite_payload = SpriteMeta(
                url=f"/api/media?path={urllib.parse.quote(str(sprite_abs), safe='')}",
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
                        "video_name": unicodedata.normalize("NFC", video_path.name),
                        "already_embedded": use_existing,
                        "sprite": sprite_payload.to_dict(),
                        "chapters": [s.to_dict() for s in segments],
                        "subtitles": [t.to_dict() for t in sub_tracks],
                        "stats": stats.to_dict(),
                        "logs": stats.logs,
                        "candidates": raw_scan.to_candidates_list(),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as exc:
            push_event(json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False))
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
