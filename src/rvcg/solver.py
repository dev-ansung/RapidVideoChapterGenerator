import math

from rvcg.models import (
    BoundaryConfig,
    PhaseProgressCallback,
    RawScanResult,
    SceneSegment,
    VisualCut,
)


def compute_cell_times(start_t: float, end_t: float, card_dur: float = 8.4) -> list[float]:
    seg_dur = max(1.0, end_t - start_t)
    margin = min(10.0, seg_dur * 0.06)
    usable = max(1.0, seg_dur - 2 * margin - card_dur)
    return [round(start_t + margin + (k / 7.0) * usable, 2) for k in range(8)]


def format_chapter_title(template: str, index: int) -> str:
    try:
        return template.format(n=index)
    except (KeyError, ValueError):
        return f"{template} {index:02d}".strip()


def place_priority_anchors(
    duration: float,
    raw: RawScanResult,
    min_seg: float,
) -> tuple[list[float], int, int]:
    anchors = [0.0, duration]
    n_black_used = 0
    for bp in sorted(raw.black_points):
        if all(abs(bp - a) >= min_seg for a in anchors):
            anchors.append(bp)
            anchors.sort()
            n_black_used += 1

    n_visual_used = 0
    for vc in sorted(raw.visual_cuts, key=lambda x: x.score, reverse=True):
        if all(abs(vc.timestamp - a) >= min_seg for a in anchors):
            anchors.append(vc.timestamp)
            anchors.sort()
            n_visual_used += 1

    return anchors, n_black_used, n_visual_used


def subdivide_long_gaps(
    anchors: list[float],
    visual_cuts: list[VisualCut],
    min_seg: float,
    max_seg: float,
    target_seg: float,
) -> tuple[list[float], int, int]:
    final_cuts = [anchors[0]]
    n_sub_cuts = 0
    n_snapped = 0
    for nxt in anchors[1:]:
        gap = nxt - final_cuts[-1]
        if gap > max_seg:
            n_sub = int(math.ceil(gap / target_seg))
            step = gap / n_sub
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
                else:
                    cut_t = target_t
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


def solve_boundaries(
    duration: float,
    raw: RawScanResult,
    config: BoundaryConfig,
    on_phase: PhaseProgressCallback | None = None,
) -> list[SceneSegment]:
    def emit(phase: int, completed: float, total: float, info: str) -> None:
        if on_phase is not None:
            on_phase(phase, completed, total, info)

    emit(3, 0.0, 1.0, "placing anchors...")
    anchors, n_black, n_visual = place_priority_anchors(duration, raw, config.min_seg)
    emit(3, 1.0, 1.0, f"{len(anchors)} anchors ({n_black} black, {n_visual} visual)")

    emit(4, 0.0, 1.0, "checking gaps...")
    cuts, n_sub, n_snapped = subdivide_long_gaps(
        anchors=anchors,
        visual_cuts=raw.visual_cuts,
        min_seg=config.min_seg,
        max_seg=config.max_seg,
        target_seg=config.target_seg,
    )
    emit(4, 1.0, 1.0, f"+{n_sub} sub-cuts ({n_snapped} snapped to visual cuts)")

    emit(5, 0.0, 1.0, "merging & sampling...")
    segments = merge_and_sample(
        cuts=cuts,
        card_dur=config.card_dur,
        title_template=config.title_template,
    )
    emit(5, 1.0, 1.0, f"{len(segments)} chapters · {len(segments) * 8} grid cells")
    return segments
