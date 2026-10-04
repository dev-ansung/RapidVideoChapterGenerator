from rvcg.models import BoundaryConfig, RawScanResult, VisualCut, fmt_hms, fmt_ms
from rvcg.solver import (
    merge_and_sample,
    place_priority_anchors,
    solve_boundaries,
    solve_boundaries_with_stats,
    subdivide_long_gaps,
)


def test_fmt_helpers() -> None:
    assert fmt_hms(0.0) == "00:00:00"
    assert fmt_hms(3661.2) == "01:01:01"
    assert fmt_ms(125.0) == "02:05"
    assert fmt_ms(3605.0) == "01:00:05"


def test_place_priority_anchors_prefers_black_and_white_fades_and_respects_min_seg() -> None:
    raw = RawScanResult(
        black_points=[300.0, 350.0],
        white_points=[500.0],
        visual_cuts=[
            VisualCut(timestamp=320.0, score=0.95),
            VisualCut(timestamp=520.0, score=0.90),
            VisualCut(timestamp=750.0, score=0.80),
        ],
    )
    anchors, n_black, n_white, n_visual = place_priority_anchors(1000.0, raw, min_seg=180.0)
    assert anchors == [0.0, 300.0, 500.0, 750.0, 1000.0]
    assert n_black == 1
    assert n_white == 1
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
    assert len(segments[0].cell_times) == 9


def test_solve_boundaries_preset_and_callback() -> None:
    cfg = BoundaryConfig.from_preset("presentation")
    assert cfg.min_seg == 60.0
    assert cfg.scene_threshold == 0.28

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


def test_solve_boundaries_stage_toggles() -> None:
    raw = RawScanResult(
        black_points=[300.0],
        white_points=[500.0],
        visual_cuts=[VisualCut(timestamp=600.0, score=0.92)],
    )
    black_only_cfg = BoundaryConfig.from_preset("movie")
    assert black_only_cfg.enable_black_fades is True
    assert black_only_cfg.enable_white_fades is True
    assert black_only_cfg.enable_visual_cuts is False
    assert black_only_cfg.enable_subdivide is False

    segs_black_only = solve_boundaries(1500.0, raw, black_only_cfg)
    assert [(s.start_time, s.end_time) for s in segs_black_only] == [(0.0, 300.0), (300.0, 500.0), (500.0, 1500.0)]

    visual_only_cfg = BoundaryConfig(
        enable_black_fades=False,
        enable_white_fades=False,
        enable_visual_cuts=True,
        enable_subdivide=False,
    )
    segs_visual_only = solve_boundaries(1500.0, raw, visual_only_cfg)
    assert [(s.start_time, s.end_time) for s in segs_visual_only] == [(0.0, 600.0), (600.0, 1500.0)]

    full_raw = RawScanResult(
        black_points=[300.0, 350.0],
        white_points=[500.0],
        visual_cuts=[VisualCut(timestamp=700.0, score=0.92), VisualCut(timestamp=1150.0, score=0.61)],
    )
    # Default is fades-only
    default_segs, default_stats = solve_boundaries_with_stats(1800.0, full_raw, BoundaryConfig())
    assert len(default_segs) == 3
    assert [s.cut_kind for s in default_segs] == ["start", "black", "white"]

    # balanced preset tests full multi-stage pipeline
    segs, stats = solve_boundaries_with_stats(1800.0, full_raw, BoundaryConfig.from_preset("balanced"))
    assert len(segs) == 7
    assert [s.cut_kind for s in segs] == ["start", "black", "white", "visual", "visual", "subdiv", "subdiv"]
    assert "Black fade" in segs[1].cut_detail
    assert "White fade" in segs[2].cut_detail
    assert "Visual cut" in segs[3].cut_detail
    assert "Subdivided" in segs[5].cut_detail
    assert stats.raw_black == 2
    assert stats.used_black == 1
    assert stats.raw_white == 1
    assert stats.used_white == 1
    assert stats.raw_visual == 2
    assert stats.used_visual == 2
    assert stats.sub_cuts == 2
    assert any("Black fade" in line for line in stats.logs)
    assert any("White fade" in line for line in stats.logs)
    assert any("Visual cut" in line for line in stats.logs)

    cands = full_raw.to_candidates_list()
    assert len(cands) == 5
    assert [c["kind"] for c in cands] == ["black", "black", "white", "visual", "visual"]
    assert [c["timestamp"] for c in cands] == [300.0, 350.0, 500.0, 700.0, 1150.0]


def test_all_presets_valid() -> None:
    from rvcg.models import PRESETS

    for name, meta in PRESETS.items():
        assert meta.id == name
        assert meta.name
        assert meta.description
        cfg = BoundaryConfig.from_preset(name)
        assert cfg.min_seg > 0
        assert cfg.max_seg >= cfg.min_seg
        assert cfg.target_seg >= cfg.min_seg
        assert 0.0 <= cfg.scene_threshold <= 1.0
