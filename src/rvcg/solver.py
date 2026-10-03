import math

from rvcg.models import (
    BoundaryConfig,
    BoundaryStats,
    PhaseProgressCallback,
    RawScanResult,
    SceneSegment,
    VisualCut,
    fmt_hms,
)


def compute_cell_times(start_t: float, end_t: float, card_dur: float = 8.4) -> list[float]:
    seg_dur = max(1.0, end_t - start_t)
    margin = min(10.0, seg_dur * 0.06)
    usable = max(1.0, seg_dur - 2 * margin - card_dur)
    return [round(start_t + margin + (k / 8.0) * usable, 2) for k in range(9)]


def format_chapter_title(template: str, index: int) -> str:
    try:
        return template.format(n=index)
    except (KeyError, ValueError):
        return f"{template} {index:02d}".strip()


def place_priority_anchors(
    duration: float,
    raw: RawScanResult,
    min_seg: float,
    enable_black_fades: bool = True,
    enable_visual_cuts: bool = True,
    logs: list[str] | None = None,
) -> tuple[list[float], int, int]:
    anchors = [0.0, duration]
    n_black_used = 0
    if enable_black_fades:
        for bp in sorted(raw.black_points):
            if all(abs(bp - a) >= min_seg for a in anchors):
                anchors.append(bp)
                anchors.sort()
                n_black_used += 1
                if logs is not None:
                    logs.append(f"[Stage 1] Black fade @ {fmt_hms(bp)} ({bp:.2f}s) -> KEPT")
            elif logs is not None:
                nearest = min(anchors, key=lambda a: abs(bp - a))
                logs.append(
                    f"[Stage 1] Black fade @ {fmt_hms(bp)} ({bp:.2f}s) -> SUPPRESSED "
                    f"({abs(bp - nearest):.1f}s from {fmt_hms(nearest)} < min {min_seg:.0f}s)"
                )
    elif logs is not None:
        logs.append("[Stage 1] Black Fades disabled")

    n_visual_used = 0
    if enable_visual_cuts:
        for vc in sorted(raw.visual_cuts, key=lambda x: x.score, reverse=True):
            if all(abs(vc.timestamp - a) >= min_seg for a in anchors):
                anchors.append(vc.timestamp)
                anchors.sort()
                n_visual_used += 1
                if logs is not None:
                    logs.append(
                        f"[Stage 2] Visual cut @ {fmt_hms(vc.timestamp)} ({vc.timestamp:.2f}s, score={vc.score:.3f}) -> KEPT"
                    )
            elif logs is not None:
                nearest = min(anchors, key=lambda a: abs(vc.timestamp - a))
                logs.append(
                    f"[Stage 2] Visual cut @ {fmt_hms(vc.timestamp)} ({vc.timestamp:.2f}s, score={vc.score:.3f}) -> SUPPRESSED "
                    f"({abs(vc.timestamp - nearest):.1f}s from {fmt_hms(nearest)} < min {min_seg:.0f}s)"
                )
    elif logs is not None:
        logs.append("[Stage 2] Visual Cuts disabled")

    return anchors, n_black_used, n_visual_used


def subdivide_long_gaps(
    anchors: list[float],
    visual_cuts: list[VisualCut],
    min_seg: float,
    max_seg: float,
    target_seg: float,
    logs: list[str] | None = None,
) -> tuple[list[float], int, int]:
    final_cuts = [anchors[0]]
    n_sub_cuts = 0
    n_snapped = 0
    for nxt in anchors[1:]:
        gap = nxt - final_cuts[-1]
        if gap > max_seg:
            n_sub = int(math.ceil(gap / target_seg))
            step = gap / n_sub
            if logs is not None:
                logs.append(
                    f"[Stage 3] Gap {fmt_hms(final_cuts[-1])}–{fmt_hms(nxt)} ({gap:.1f}s > max {max_seg:.0f}s) -> splitting into {n_sub} parts"
                )
            for _ in range(1, n_sub):
                target_t = final_cuts[-1] + step
                best_sc = [
                    vc.timestamp
                    for vc in visual_cuts
                    if abs(vc.timestamp - target_t) <= 45.0
                    and (vc.timestamp - final_cuts[-1]) >= min_seg * 0.75
                    and (nxt - vc.timestamp) >= min_seg * 0.75
                ]
                if best_sc:
                    cut_t = min(best_sc, key=lambda x: abs(x - target_t))
                    n_snapped += 1
                    if logs is not None:
                        logs.append(
                            f"[Stage 3]   Sub-cut @ {fmt_hms(cut_t)} ({cut_t:.2f}s, snapped from target {fmt_hms(target_t)})"
                        )
                else:
                    cut_t = target_t
                    if logs is not None:
                        logs.append(f"[Stage 3]   Sub-cut @ {fmt_hms(cut_t)} ({cut_t:.2f}s, uniform step)")
                final_cuts.append(round(cut_t, 2))
                n_sub_cuts += 1
        final_cuts.append(round(nxt, 2))
    return final_cuts, n_sub_cuts, n_snapped


def merge_and_sample(
    cuts: list[float],
    card_dur: float = 8.4,
    min_tail: float = 20.0,
    title_template: str = "Scene {n:02d}",
) -> list[SceneSegment]:
    raw_pairs: list[tuple[float, float]] = []
    for idx in range(len(cuts) - 1):
        s, e = cuts[idx], cuts[idx + 1]
        if e - s < min_tail and raw_pairs:
            prev_s, _ = raw_pairs[-1]
            raw_pairs[-1] = (prev_s, e)
        else:
            raw_pairs.append((s, e))

    segments: list[SceneSegment] = []
    for idx, (s, e) in enumerate(raw_pairs, 1):
        segments.append(
            SceneSegment(
                index=idx,
                start_time=round(s, 2),
                end_time=round(e, 2),
                title=format_chapter_title(title_template, idx),
                cell_times=compute_cell_times(s, e, card_dur),
                card_dur=card_dur,
            )
        )
    return segments


def segments_from_tuples(
    raw_tuples: list[tuple[float, float, str]],
    card_dur: float = 8.4,
) -> list[SceneSegment]:
    return [
        SceneSegment(
            index=idx,
            start_time=round(s, 2),
            end_time=round(e, 2),
            title=title,
            cell_times=compute_cell_times(s, e, card_dur),
            card_dur=card_dur,
        )
        for idx, (s, e, title) in enumerate(raw_tuples, 1)
    ]


def solve_boundaries_with_stats(
    duration: float,
    raw: RawScanResult,
    config: BoundaryConfig,
    on_phase: PhaseProgressCallback | None = None,
) -> tuple[list[SceneSegment], BoundaryStats]:
    def emit(phase: int, completed: float, total: float, info: str) -> None:
        if on_phase is not None:
            on_phase(phase, completed, total, info)

    logs: list[str] = [
        f"[Scan] Raw candidates: {len(raw.black_points)} black fades, {len(raw.visual_cuts)} visual cuts (duration={fmt_hms(duration)})"
    ]

    emit(3, 0.0, 1.0, "placing anchors...")
    anchors, n_black, n_visual = place_priority_anchors(
        duration,
        raw,
        config.min_seg,
        enable_black_fades=config.enable_black_fades,
        enable_visual_cuts=config.enable_visual_cuts,
        logs=logs,
    )
    emit(3, 1.0, 1.0, f"{len(anchors)} anchors ({n_black} black, {n_visual} visual)")

    emit(4, 0.0, 1.0, "checking gaps...")
    n_sub = 0
    n_snapped = 0
    if config.enable_subdivide:
        cuts, n_sub, n_snapped = subdivide_long_gaps(
            anchors=anchors,
            visual_cuts=raw.visual_cuts if config.enable_visual_cuts else [],
            min_seg=config.min_seg,
            max_seg=config.max_seg,
            target_seg=config.target_seg,
            logs=logs,
        )
        emit(4, 1.0, 1.0, f"+{n_sub} sub-cuts ({n_snapped} snapped to visual cuts)")
    else:
        cuts = [round(a, 2) for a in anchors]
        logs.append("[Stage 3] Subdivide Long disabled")
        emit(4, 1.0, 1.0, "skipped (subdivide off)")

    emit(5, 0.0, 1.0, "merging & sampling...")
    segments = merge_and_sample(
        cuts=cuts,
        card_dur=config.card_dur,
        title_template=config.title_template,
    )
    for seg in segments:
        logs.append(f"[Result] #{seg.id_str} {seg.title}: {seg.source_range} ({seg.duration_str})")
    emit(5, 1.0, 1.0, f"{len(segments)} chapters · {len(segments) * 9} grid cells")

    stats = BoundaryStats(
        raw_black=len(raw.black_points),
        used_black=n_black,
        raw_visual=len(raw.visual_cuts),
        used_visual=n_visual,
        sub_cuts=n_sub,
        snapped_cuts=n_snapped,
        logs=logs,
    )
    return segments, stats


def solve_boundaries(
    duration: float,
    raw: RawScanResult,
    config: BoundaryConfig,
    on_phase: PhaseProgressCallback | None = None,
) -> list[SceneSegment]:
    segments, _ = solve_boundaries_with_stats(duration, raw, config, on_phase)
    return segments
