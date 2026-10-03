from rvcg.models import BoundaryConfig, RawScanResult, VisualCut, fmt_hms, fmt_ms
from rvcg.solver import (
    merge_and_sample,
    place_priority_anchors,
    solve_boundaries,
    subdivide_long_gaps,
)


def test_fmt_helpers() -> None:
    assert fmt_hms(0.0) == "00:00:00"
    assert fmt_hms(3661.2) == "01:01:01"
    assert fmt_ms(125.0) == "02:05"
    assert fmt_ms(3605.0) == "01:00:05"


def test_place_priority_anchors_prefers_black_fades_and_respects_min_seg() -> None:
    raw = RawScanResult(
        black_points=[300.0, 350.0, 700.0],
        visual_cuts=[
            VisualCut(timestamp=320.0, score=0.95),
            VisualCut(timestamp=500.0, score=0.80),
            VisualCut(timestamp=520.0, score=0.90),
        ],
    )
    anchors, n_black, n_visual = place_priority_anchors(1000.0, raw, min_seg=180.0)
    assert anchors == [0.0, 300.0, 520.0, 700.0, 1000.0]
    assert n_black == 2
    assert n_visual == 1


def test_subdivide_long_gaps_snaps_to_visual_cut() -> None:
    anchors = [0.0, 1000.0]
    visual_cuts = [VisualCut(timestamp=350.0, score=0.55), VisualCut(timestamp=675.0, score=0.62)]
    cuts, n_sub, n_snapped = subdivide_long_gaps(
        anchors=anchors,
        visual_cuts=visual_cuts,
        min_seg=180.0,
        max_seg=600.0,
        target_seg=360.0,
    )
    assert n_sub == 2
    assert n_snapped == 2
    assert cuts == [0.0, 350.0, 675.0, 1000.0]


def test_merge_and_sample_merges_short_tail() -> None:
    cuts = [0.0, 400.0, 412.0]
    segments = merge_and_sample(cuts, title_template="Chapter {n}")
    assert len(segments) == 1
    assert segments[0].start_time == 0.0
    assert segments[0].end_time == 412.0
    assert segments[0].title == "Chapter 1"
    assert len(segments[0].cell_times) == 8


def test_solve_boundaries_preset_and_callback() -> None:
    cfg = BoundaryConfig.from_preset("presentation")
    assert cfg.min_seg == 60.0
    assert cfg.scene_threshold == 0.30

    events: list[int] = []
    raw = RawScanResult(black_points=[200.0], visual_cuts=[])
    segs = solve_boundaries(
        400.0,
        raw,
        cfg,
        on_phase=lambda phase, _c, _t, _i: events.append(phase),
    )
    assert len(segs) == 2
    assert 3 in events and 4 in events and 5 in events
