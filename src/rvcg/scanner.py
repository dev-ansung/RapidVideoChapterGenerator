import math
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from rvcg.models import (
    BoundaryConfig,
    PhaseProgressCallback,
    RawScanResult,
    SpriteMeta,
    SpriteProgressCallback,
    VisualCut,
)
from rvcg.probe import safe_float


@dataclass(frozen=True)
class ChunkSpec:
    worker_id: int
    t_start: float
    t_end: float
    n_rows: int
    strip_path: Path | None


@dataclass(frozen=True)
class LineParseEvent:
    black_midpoints: list[float] = field(default_factory=list)
    visual_cuts: list[VisualCut] = field(default_factory=list)
    new_local_t: float | None = None
    progress_sec: float | None = None

    @property
    def updated(self) -> bool:
        return bool(self.black_midpoints or self.visual_cuts or self.progress_sec is not None)


def compute_chunks(
    duration: float,
    total_rows: int,
    row_dur: int,
    workers: int,
    thumbs_dir: Path | None = None,
) -> list[ChunkSpec]:
    actual_workers = max(1, min(workers, total_rows))
    rows_per_worker = int(math.ceil(total_rows / actual_workers))
    chunks: list[ChunkSpec] = []
    for w in range(actual_workers):
        r_start = w * rows_per_worker
        r_end = min(total_rows, (w + 1) * rows_per_worker)
        if r_start >= r_end:
            break
        t_start = float(r_start * row_dur)
        t_end = min(duration, float(r_end * row_dur))
        n_rows = r_end - r_start
        strip = (thumbs_dir / f"_strip_{w}.jpg") if thumbs_dir is not None else None
        chunks.append(
            ChunkSpec(
                worker_id=w,
                t_start=t_start,
                t_end=t_end,
                n_rows=n_rows,
                strip_path=strip,
            )
        )
    return chunks


def parse_ffmpeg_line(
    line: str,
    t_start: float,
    chunk_dur: float,
    cur_local_t: float | None,
) -> LineParseEvent:
    blacks: list[float] = []
    cuts: list[VisualCut] = []
    next_local_t = cur_local_t
    prog_sec: float | None = None

    for m in re.finditer(
        r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)",
        line,
    ):
        bs = safe_float(m.group(1))
        be = safe_float(m.group(2))
        if bs is not None and be is not None:
            blacks.append(t_start + (bs + be) / 2.0)

    m_pts = re.search(r"pts_time:([^\s]+)", line)
    if m_pts:
        parsed_pts = safe_float(m_pts.group(1))
        if parsed_pts is not None:
            next_local_t = parsed_pts
            prog_sec = min(chunk_dur, parsed_pts)

    m_sc = re.search(r"lavfi\.scene_score=([^\s]+)", line)
    if m_sc and next_local_t is not None:
        parsed_sc = safe_float(m_sc.group(1))
        if parsed_sc is not None:
            cuts.append(VisualCut(timestamp=t_start + next_local_t, score=parsed_sc))

    if line.startswith("out_time_us="):
        raw_us = safe_float(line.split("=", 1)[1].strip())
        if raw_us is not None and raw_us >= 0:
            prog_sec = min(chunk_dur, raw_us / 1_000_000.0)

    return LineParseEvent(
        black_midpoints=blacks,
        visual_cuts=cuts,
        new_local_t=next_local_t,
        progress_sec=prog_sec,
    )


def scan_keyframes(
    video_path: Path,
    duration: float,
    config: BoundaryConfig,
    out_dir: Path | None = None,
    build_sprite: bool = False,
    skip_boundary_scan: bool = False,
    on_phase: PhaseProgressCallback | None = None,
    on_sprite: SpriteProgressCallback | None = None,
) -> tuple[RawScanResult, SpriteMeta | None]:
    def emit(phase: int, completed: float, total: float, info: str) -> None:
        if on_phase is not None:
            on_phase(phase, completed, total, info)

    interval = max(2, int(math.ceil(duration / 1400.0)))
    cols = 10
    total_frames = max(1, int(math.ceil(duration / interval)))
    total_rows = max(1, int(math.ceil(total_frames / cols)))
    row_dur = cols * interval
    thumbs_dir = (out_dir / "thumbs") if (build_sprite and out_dir is not None) else None
    if thumbs_dir is not None:
        thumbs_dir.mkdir(parents=True, exist_ok=True)

    chunks = compute_chunks(duration, total_rows, row_dur, config.workers, thumbs_dir)
    lock = threading.Lock()
    worker_prog = {c.worker_id: 0.0 for c in chunks}
    worker_blacks: dict[int, list[float]] = {c.worker_id: [] for c in chunks}
    worker_cuts: dict[int, list[VisualCut]] = {c.worker_id: [] for c in chunks}

    def run_chunk(spec: ChunkSpec) -> Path | None:
        chunk_dur = max(0.1, spec.t_end - spec.t_start)
        th = config.scene_threshold
        bd = max(0.05, config.black_min_dur)
        if skip_boundary_scan and spec.strip_path is not None:
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-nostats",
                "-progress",
                "pipe:1",
                "-ss",
                f"{spec.t_start:.2f}",
                "-t",
                f"{chunk_dur:.2f}",
                "-skip_frame",
                "nokey",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{interval},scale=240:135:flags=fast_bilinear,tile={cols}x{spec.n_rows}",
                "-frames:v",
                "1",
                "-update",
                "1",
                "-q:v",
                "4",
                str(spec.strip_path),
            ]
        elif spec.strip_path is not None:
            fc = (
                f"[0:v]scale=240:135:flags=fast_bilinear,split=2[vd][vs];"
                f"[vd]blackdetect=d={bd}:pix_th=0.12:pic_th=0.82,select='gt(scene,{th})',metadata=print:file=-[vnull];"
                f"[vs]fps=1/{interval},tile={cols}x{spec.n_rows}[vspr]"
            )
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-nostats",
                "-progress",
                "pipe:1",
                "-ss",
                f"{spec.t_start:.2f}",
                "-t",
                f"{chunk_dur:.2f}",
                "-skip_frame",
                "nokey",
                "-i",
                str(video_path),
                "-filter_complex",
                fc,
                "-map",
                "[vnull]",
                "-f",
                "null",
                "-",
                "-map",
                "[vspr]",
                "-frames:v",
                "1",
                "-update",
                "1",
                "-q:v",
                "4",
                str(spec.strip_path),
            ]
        else:
            vf = (
                f"scale=240:135:flags=fast_bilinear,"
                f"blackdetect=d={bd}:pix_th=0.12:pic_th=0.82,"
                f"select='gt(scene,{th})',"
                f"metadata=print:file=-"
            )
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-nostats",
                "-progress",
                "pipe:1",
                "-ss",
                f"{spec.t_start:.2f}",
                "-t",
                f"{chunk_dur:.2f}",
                "-skip_frame",
                "nokey",
                "-i",
                str(video_path),
                "-vf",
                vf,
                "-an",
                "-sn",
                "-f",
                "null",
                "-",
            ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        cur_local_t: float | None = None
        assert proc.stdout is not None
        for line in proc.stdout:
            ev = parse_ffmpeg_line(line, spec.t_start, chunk_dur, cur_local_t)
            cur_local_t = ev.new_local_t
            if ev.updated:
                with lock:
                    if not skip_boundary_scan:
                        worker_blacks[spec.worker_id].extend(ev.black_midpoints)
                        worker_cuts[spec.worker_id].extend(ev.visual_cuts)
                    if ev.progress_sec is not None:
                        worker_prog[spec.worker_id] = max(worker_prog[spec.worker_id], ev.progress_sec)
                    tot_prog = min(duration, sum(worker_prog.values()))
                    n_b = sum(len(v) for v in worker_blacks.values())
                    n_c = sum(len(v) for v in worker_cuts.values())
                if not skip_boundary_scan:
                    emit(2, tot_prog, duration, f"{n_b} black fades · {n_c} visual cuts")
                if on_sprite is not None:
                    on_sprite(tot_prog)

        proc.wait()
        with lock:
            worker_prog[spec.worker_id] = chunk_dur
            tot_prog = min(duration, sum(worker_prog.values()))
            n_b = sum(len(v) for v in worker_blacks.values())
            n_c = sum(len(v) for v in worker_cuts.values())
        if not skip_boundary_scan:
            emit(2, tot_prog, duration, f"{n_b} black fades · {n_c} visual cuts")
        if on_sprite is not None:
            on_sprite(tot_prog)
        return spec.strip_path

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        strip_paths = list(pool.map(run_chunk, chunks))

    sprite_meta: SpriteMeta | None = None
    if build_sprite and out_dir is not None:
        sprite_rel = "thumbs/sprite_full.jpg"
        sprite_abs = out_dir / sprite_rel
        valid_strips = [p for p in strip_paths if p is not None and p.exists()]
        if len(valid_strips) == 1:
            valid_strips[0].replace(sprite_abs)
        elif len(valid_strips) > 1:
            inputs: list[str] = []
            for sp in valid_strips:
                inputs.extend(["-i", str(sp)])
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-v",
                    "error",
                    *inputs,
                    "-filter_complex",
                    f"vstack=inputs={len(valid_strips)}",
                    "-q:v",
                    "4",
                    str(sprite_abs),
                ],
                stdin=subprocess.DEVNULL,
                check=True,
            )
            for sp in valid_strips:
                sp.unlink(missing_ok=True)
        sprite_meta = SpriteMeta(
            url=sprite_rel,
            interval=interval,
            cols=cols,
            rows=total_rows,
            total_frames=total_frames,
        )
        if on_sprite is not None:
            on_sprite(duration)

    raw_res = RawScanResult(
        black_points=sorted(b for w in sorted(worker_blacks) for b in worker_blacks[w]),
        visual_cuts=[c for w in sorted(worker_cuts) for c in worker_cuts[w]],
    )
    if not skip_boundary_scan:
        emit(
            2,
            duration,
            duration,
            f"{len(raw_res.black_points)} black fades · {len(raw_res.visual_cuts)} visual cuts",
        )
    return raw_res, sprite_meta


@dataclass(frozen=True)
class PrecisionTransition:
    timestamp: float
    kind: str
    score: float
    label: str

    def to_dict(self) -> dict[str, str | float]:
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "score": self.score,
            "label": self.label,
        }


def _scan_slice_transitions(
    video_path: Path,
    t_start: float,
    slice_dur: float,
    threshold: float,
    black_min_dur: float,
) -> list[PrecisionTransition]:
    if slice_dur <= 0.05:
        return []
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "info",
        "-ss",
        f"{t_start:.3f}",
        "-t",
        f"{slice_dur:.3f}",
        "-i",
        str(video_path),
        "-vf",
        f"scale=320:180:flags=fast_bilinear,select=gt(scene\\,{threshold:.3f}),showinfo,blackdetect=d={black_min_dur:.2f}:pic_th=0.98:pix_th=0.10",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
    results: list[PrecisionTransition] = []
    lines = proc.stderr.splitlines()

    for line in lines:
        for m_b in re.finditer(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)", line):
            bs = safe_float(m_b.group(1))
            be = safe_float(m_b.group(2))
            if bs is not None and be is not None:
                ts = round(t_start + (bs + be) / 2.0, 3)
                results.append(PrecisionTransition(timestamp=ts, kind="black", score=2.0, label="Black Fade"))

        m_pts = re.search(r"pts_time:([0-9.]+)", line)
        if m_pts:
            pts = safe_float(m_pts.group(1))
            if pts is not None:
                ts = round(t_start + pts, 3)
                m_sc = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
                sc = safe_float(m_sc.group(1)) if m_sc else 0.50
                score_val = sc if sc is not None else 0.50
                results.append(
                    PrecisionTransition(
                        timestamp=ts,
                        kind="visual",
                        score=round(score_val, 3),
                        label=f"Visual {score_val:.2f}",
                    )
                )

    # Deduplicate within 0.08s
    deduped: list[PrecisionTransition] = []
    results.sort(key=lambda x: x.timestamp)
    for r in results:
        if not any(abs(r.timestamp - ex.timestamp) < 0.08 for ex in deduped):
            deduped.append(r)
    return deduped


def find_precision_transition(
    video_path: Path,
    current_time: float,
    direction: str,
    window_sec: float = 30.0,
    threshold: float = 0.20,
    black_min_dur: float = 0.20,
) -> PrecisionTransition | None:
    norm_dir = direction.strip().lower()
    if norm_dir == "prev":
        t_start = max(0.0, current_time - window_sec)
        slice_dur = current_time - t_start
        cuts = _scan_slice_transitions(video_path, t_start, slice_dur, threshold, black_min_dur)
        matches = [c for c in cuts if c.timestamp < current_time - 0.05]
        if matches:
            return matches[-1]
        # Expand window if not found
        if t_start > 0:
            exp_start = max(0.0, current_time - (window_sec * 3.0))
            exp_dur = t_start - exp_start
            exp_cuts = _scan_slice_transitions(video_path, exp_start, exp_dur, threshold, black_min_dur)
            exp_matches = [c for c in exp_cuts if c.timestamp < current_time - 0.05]
            if exp_matches:
                return exp_matches[-1]
    else:
        t_start = current_time
        slice_dur = window_sec
        cuts = _scan_slice_transitions(video_path, t_start, slice_dur, threshold, black_min_dur)
        matches = [c for c in cuts if c.timestamp > current_time + 0.05]
        if matches:
            return matches[0]
        # Expand window if not found
        exp_start = current_time + window_sec
        exp_cuts = _scan_slice_transitions(video_path, exp_start, window_sec * 2.0, threshold, black_min_dur)
        exp_matches = [c for c in exp_cuts if c.timestamp > current_time + 0.05]
        if exp_matches:
            return exp_matches[0]
    return None
