import math
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from rvcg.models import (
    BoundaryConfig,
    FadePoint,
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
    black_midpoints: list[FadePoint] = field(default_factory=list)
    white_midpoints: list[FadePoint] = field(default_factory=list)
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
    blacks: list[FadePoint] = []
    whites: list[FadePoint] = []
    cuts: list[VisualCut] = []
    next_local_t = cur_local_t
    prog_sec: float | None = None

    for m in re.finditer(
        r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)",
        line,
    ):
        bs = safe_float(m.group(1))
        be = safe_float(m.group(2))
        bd = safe_float(m.group(3)) or (be - bs if bs is not None and be is not None else 0.0)
        if bs is not None and be is not None:
            mid = t_start + (bs + be) / 2.0
            fp = FadePoint(timestamp=mid, duration=bd)
            if (
                is_white
                or "Parsed_blackdetect_6" in line
                or "Parsed_blackdetect_5" in line
                or "Parsed_blackdetect_4" in line
                or "white" in line.lower()
            ):
                whites.append(fp)
            else:
                blacks.append(fp)

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
    worker_blacks: dict[int, list[FadePoint]] = {c.worker_id: [] for c in chunks}
    worker_whites: dict[int, list[FadePoint]] = {c.worker_id: [] for c in chunks}
    worker_cuts: dict[int, list[VisualCut]] = {c.worker_id: [] for c in chunks}

    if not skip_boundary_scan:
        emit(2, 0.0, duration, "0 black · 0 white · 0 visual cuts")

        def run_chunk(spec: ChunkSpec) -> None:
            chunk_dur = max(0.1, spec.t_end - spec.t_start)
            th = config.scene_threshold
            bd = max(0.05, config.black_min_dur)
            with_sprite = build_sprite and spec.strip_path is not None
            blk_pic_th = config.black_pic_th
            wht_pic_th = config.white_pic_th
            blk_pix_th = config.black_pix_th
            wht_pix_th = config.white_pix_th
            if with_sprite and spec.strip_path is not None:
                fc = (
                    f"[0:v]scale=240:135:flags=fast_bilinear,split=3[vd_blk][vd_wht][vs];"
                    f"[vd_blk]blackdetect=d={bd}:pix_th={blk_pix_th}:pic_th={blk_pic_th},select='gt(scene,{th})',metadata=print:file=-[vnull1];"
                    f"[vd_wht]negate,blackdetect=d={max(0.10, bd * 0.75):.2f}:pic_th={wht_pic_th}:pix_th={wht_pix_th},metadata=print:key=lavfi.black_start:file=-[vnull2];"
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
                    "[vnull1]",
                    "-f",
                    "null",
                    "-",
                    "-map",
                    "[vnull2]",
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
                fc = (
                    f"[0:v]scale=240:135:flags=fast_bilinear,split=2[vd_blk][vd_wht];"
                    f"[vd_blk]blackdetect=d={bd}:pix_th={blk_pix_th}:pic_th={blk_pic_th},select='gt(scene,{th})',metadata=print:file=-[vnull1];"
                    f"[vd_wht]negate,blackdetect=d={max(0.10, bd * 0.75):.2f}:pic_th={wht_pic_th}:pix_th={wht_pix_th},metadata=print:key=lavfi.black_start:file=-[vnull2]"
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
                        tot_prog = min(duration * 0.99, sum(worker_prog.values()))
                        n_b = sum(len(v) for v in worker_blacks.values())
                        n_w = sum(len(v) for v in worker_whites.values())
                        n_c = sum(len(v) for v in worker_cuts.values())
                    emit(2, tot_prog, duration, f"{n_b} black · {n_w} white · {n_c} visual cuts")
                    if with_sprite and on_sprite is not None:
                        on_sprite(tot_prog)

            proc.wait()
            with lock:
                worker_prog[spec.worker_id] = chunk_dur
                tot_prog = min(duration * 0.99, sum(worker_prog.values()))
                n_b = sum(len(v) for v in worker_blacks.values())
                n_w = sum(len(v) for v in worker_whites.values())
                n_c = sum(len(v) for v in worker_cuts.values())
            emit(2, tot_prog, duration, f"{n_b} black · {n_w} white · {n_c} visual cuts")
            if with_sprite and on_sprite is not None:
                on_sprite(tot_prog)

        with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
            list(pool.map(run_chunk, chunks))

    elif build_sprite and out_dir is not None:

        def run_sprite_only_chunk(spec: ChunkSpec) -> None:
            if spec.strip_path is None:
                return
            chunk_dur = max(0.1, spec.t_end - spec.t_start)
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
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                if line.startswith("out_time_us="):
                    raw_us = safe_float(line.split("=", 1)[1].strip())
                    if raw_us is not None and raw_us >= 0:
                        prog = min(chunk_dur, raw_us / 1_000_000.0)
                        with lock:
                            worker_prog[spec.worker_id] = max(worker_prog[spec.worker_id], prog)
                            tot_prog = min(duration * 0.99, sum(worker_prog.values()))
                        if on_sprite is not None:
                            on_sprite(tot_prog)
            proc.wait()
            with lock:
                worker_prog[spec.worker_id] = chunk_dur
                tot_prog = min(duration * 0.99, sum(worker_prog.values()))
            if on_sprite is not None:
                on_sprite(tot_prog)

        with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
            list(pool.map(run_sprite_only_chunk, chunks))

    sprite_meta: SpriteMeta | None = None
    if build_sprite and out_dir is not None:
        sprite_rel = "thumbs/sprite_full.jpg"
        sprite_abs = out_dir / sprite_rel
        valid_strips = [c.strip_path for c in chunks if c.strip_path is not None and c.strip_path.exists()]
        if len(valid_strips) == 1:
            valid_strips[0].replace(sprite_abs)
        elif len(valid_strips) > 1:
            if on_sprite is not None:
                on_sprite(duration * 0.95)
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
            f"{len(raw_res.black_points)} black · {len(raw_res.white_points)} white · {len(raw_res.visual_cuts)} visual cuts",
        )
    return raw_res, sprite_meta
