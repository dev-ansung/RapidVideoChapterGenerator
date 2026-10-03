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
    white_midpoints: list[float] = field(default_factory=list)
    visual_cuts: list[VisualCut] = field(default_factory=list)
    new_local_t: float | None = None
    progress_sec: float | None = None

    @property
    def updated(self) -> bool:
        return bool(self.black_midpoints or self.white_midpoints or self.visual_cuts or self.progress_sec is not None)


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
    is_white: bool = False,
    scene_threshold: float = 0.0,
) -> LineParseEvent:
    blacks: list[float] = []
    whites: list[float] = []
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
            mid = t_start + (bs + be) / 2.0
            if (
                is_white
                or "Parsed_blackdetect_6" in line
                or "Parsed_blackdetect_5" in line
                or "Parsed_blackdetect_4" in line
                or "white" in line.lower()
            ):
                whites.append(mid)
            else:
                blacks.append(mid)

    m_pts = re.search(r"pts_time:([^\s]+)", line)
    if m_pts:
        parsed_pts = safe_float(m_pts.group(1))
        if parsed_pts is not None:
            next_local_t = parsed_pts
            prog_sec = min(chunk_dur, parsed_pts)

    m_sc = re.search(r"lavfi\.scene_score=([^\s]+)", line)
    if m_sc and next_local_t is not None:
        parsed_sc = safe_float(m_sc.group(1))
        if parsed_sc is not None and parsed_sc >= scene_threshold:
            cuts.append(VisualCut(timestamp=t_start + next_local_t, score=parsed_sc))

    if line.startswith("out_time_us="):
        raw_us = safe_float(line.split("=", 1)[1].strip())
        if raw_us is not None and raw_us >= 0:
            prog_sec = min(chunk_dur, raw_us / 1_000_000.0)

    return LineParseEvent(
        black_midpoints=blacks,
        white_midpoints=whites,
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
    worker_whites: dict[int, list[float]] = {c.worker_id: [] for c in chunks}
    worker_cuts: dict[int, list[VisualCut]] = {c.worker_id: [] for c in chunks}

    if not skip_boundary_scan:

        def run_boundary_chunk(spec: ChunkSpec) -> None:
            chunk_dur = max(0.1, spec.t_end - spec.t_start)
            th = config.scene_threshold
            bd = max(0.05, config.black_min_dur)
            fc = (
                f"[0:v]scale=240:135:flags=fast_bilinear,split=2[vd_blk][vd_wht];"
                f"[vd_blk]blackdetect=d={bd}:pix_th=0.12:pic_th=0.82,select='gte(scene,0)',metadata=print:file=-[vnull1];"
                f"[vd_wht]negate,blackdetect=d={max(0.10, bd * 0.75):.2f}:pic_th=0.85:pix_th=0.25,metadata=print:key=lavfi.black_start:file=-[vnull2]"
            )
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-nostats",
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
                "[vnull1]",
                "-f",
                "null",
                "-",
                "-map",
                "[vnull2]",
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
                ev = parse_ffmpeg_line(line, spec.t_start, chunk_dur, cur_local_t, scene_threshold=th)
                cur_local_t = ev.new_local_t
                if ev.updated:
                    with lock:
                        worker_blacks[spec.worker_id].extend(ev.black_midpoints)
                        worker_whites[spec.worker_id].extend(ev.white_midpoints)
                        worker_cuts[spec.worker_id].extend(ev.visual_cuts)
                        if ev.progress_sec is not None:
                            worker_prog[spec.worker_id] = max(worker_prog[spec.worker_id], ev.progress_sec)
                        tot_prog = min(duration, sum(worker_prog.values()))
                        n_b = sum(len(v) for v in worker_blacks.values())
                        n_w = sum(len(v) for v in worker_whites.values())
                        n_c = sum(len(v) for v in worker_cuts.values())
                    emit(2, tot_prog, duration, f"{n_b} black · {n_w} white · {n_c} visual cuts")

            proc.wait()
            with lock:
                worker_prog[spec.worker_id] = chunk_dur
                tot_prog = min(duration, sum(worker_prog.values()))
                n_b = sum(len(v) for v in worker_blacks.values())
                n_w = sum(len(v) for v in worker_whites.values())
                n_c = sum(len(v) for v in worker_cuts.values())
            emit(2, tot_prog, duration, f"{n_b} black · {n_w} white · {n_c} visual cuts")

        with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
            list(pool.map(run_boundary_chunk, chunks))

    sprite_meta: SpriteMeta | None = None
    if build_sprite and out_dir is not None:
        sprite_prog = {c.worker_id: 0.0 for c in chunks}
        sprite_lock = threading.Lock()

        def run_sprite_chunk(spec: ChunkSpec) -> Path | None:
            if spec.strip_path is None:
                return None
            chunk_dur = max(0.1, spec.t_end - spec.t_start)
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{spec.t_start:.2f}",
                "-skip_frame",
                "nokey",
                "-i",
                str(video_path),
                "-t",
                f"{chunk_dur:.2f}",
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
            subprocess.run(cmd, stdin=subprocess.DEVNULL, check=False)
            with sprite_lock:
                sprite_prog[spec.worker_id] = chunk_dur
                if on_sprite is not None:
                    on_sprite(min(duration, sum(sprite_prog.values())))
            return spec.strip_path

        with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
            strip_paths = list(pool.map(run_sprite_chunk, chunks))

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
        white_points=sorted(b for w in sorted(worker_whites) for b in worker_whites[w]),
        visual_cuts=[c for w in sorted(worker_cuts) for c in worker_cuts[w]],
    )
    if not skip_boundary_scan:
        emit(
            2,
            duration,
            duration,
            f"{len(raw_res.black_points)} black · {len(raw_res.white_points)} white · {len(raw_res.visual_cuts)} visual",
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
        "-copyts",
        "-i",
        str(video_path),
        "-filter_complex",
        f"[0:v]scale=320:180:flags=fast_bilinear,split=3[v_cut][v_black][v_white];"
        f"[v_cut]select=gt(scene\\,{threshold:.3f}),showinfo[out_cut];"
        f"[v_black]blackdetect=d={black_min_dur:.2f}:pic_th=0.98:pix_th=0.10[out_black];"
        f"[v_white]negate,blackdetect=d={max(0.10, black_min_dur * 0.75):.2f}:pic_th=0.85:pix_th=0.25[out_white]",
        "-map",
        "[out_cut]",
        "-f",
        "null",
        "-",
        "-map",
        "[out_black]",
        "-f",
        "null",
        "-",
        "-map",
        "[out_white]",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
    results: list[PrecisionTransition] = []
    lines = proc.stderr.splitlines()

    for line in lines:
        if "Parsed_blackdetect_6" in line or "Parsed_blackdetect_5" in line:
            m_w = re.search(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)", line)
            if m_w:
                bs = safe_float(m_w.group(1))
                be = safe_float(m_w.group(2))
                if bs is not None and be is not None:
                    ts = round((bs + be) / 2.0, 3)
                    results.append(PrecisionTransition(timestamp=ts, kind="white", score=2.0, label="White Fade"))
        elif "black_start" in line:
            for m_b in re.finditer(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)", line):
                bs = safe_float(m_b.group(1))
                be = safe_float(m_b.group(2))
                if bs is not None and be is not None:
                    ts = round((bs + be) / 2.0, 3)
                    results.append(PrecisionTransition(timestamp=ts, kind="black", score=2.0, label="Black Fade"))

        m_pts = re.search(r"pts_time:([0-9.]+)", line)
        if m_pts and "Parsed_showinfo" in line:
            pts = safe_float(m_pts.group(1))
            if pts is not None:
                ts = round(pts, 3)
                m_sc = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
                sc = safe_float(m_sc.group(1)) if m_sc else threshold
                score_val = sc if sc is not None else threshold
                results.append(
                    PrecisionTransition(
                        timestamp=ts,
                        kind="visual",
                        score=round(score_val, 3),
                        label=f"Visual {score_val:.2f}",
                    )
                )

    # Deduplicate within 0.08s (favor black/white fades over adjacent raw cuts)
    results.sort(key=lambda x: (x.timestamp, -x.score))
    deduped: list[PrecisionTransition] = []
    for r in results:
        if not any(abs(r.timestamp - ex.timestamp) < 0.08 for ex in deduped):
            deduped.append(r)
    return deduped


def find_precision_transition(
    video_path: Path,
    current_time: float,
    direction: str,
    window_sec: float = 45.0,
    threshold: float = 0.15,
    black_min_dur: float = 0.20,
) -> PrecisionTransition | None:
    norm_dir = direction.strip().lower()
    windows = [window_sec, window_sec * 4.0, window_sec * 10.0]

    if norm_dir == "prev":
        for win in windows:
            t_start = max(0.0, current_time - win)
            slice_dur = current_time - t_start
            if slice_dur <= 0.05:
                break
            cuts = _scan_slice_transitions(video_path, t_start, slice_dur, threshold, black_min_dur)
            matches = [c for c in cuts if c.timestamp < current_time - 0.05]
            if matches:
                return matches[-1]
            if t_start == 0.0:
                break
    else:
        for win in windows:
            t_start = current_time
            cuts = _scan_slice_transitions(video_path, t_start, win, threshold, black_min_dur)
            matches = [c for c in cuts if c.timestamp > current_time + 0.05]
            if matches:
                return matches[0]
            if len(cuts) == 0 and win == windows[-1]:
                soft_cuts = _scan_slice_transitions(video_path, t_start, win, max(0.08, threshold * 0.7), black_min_dur)
                soft_matches = [c for c in soft_cuts if c.timestamp > current_time + 0.05]
                if soft_matches:
                    return soft_matches[0]
    return None
