from pathlib import Path

from rvcg.scanner import compute_chunks, parse_ffmpeg_line


def test_compute_chunks_row_aligned(tmp_path: Path) -> None:
    chunks = compute_chunks(duration=1000.0, total_rows=10, row_dur=100, workers=4, thumbs_dir=tmp_path)
    assert len(chunks) == 4
    assert chunks[0].t_start == 0.0
    assert chunks[0].t_end == 300.0
    assert chunks[0].n_rows == 3
    assert chunks[-1].t_end == 1000.0


def test_parse_ffmpeg_line_events() -> None:
    ev_black = parse_ffmpeg_line(
        "black_start:10.0 black_end:12.0 black_duration:2.0",
        t_start=100.0,
        chunk_dur=300.0,
        cur_local_t=None,
        is_white=False,
    )
    assert ev_black.black_midpoints == [111.0]
    assert ev_black.white_midpoints == []

    ev_white = parse_ffmpeg_line(
        "black_start:5.0 black_end:7.0 black_duration:2.0",
        t_start=100.0,
        chunk_dur=300.0,
        cur_local_t=None,
        is_white=True,
    )
    assert ev_white.white_midpoints == [106.0]
    assert ev_white.black_midpoints == []

    ev_pts = parse_ffmpeg_line(
        "frame:12 pts:1200 pts_time:45.5",
        t_start=100.0,
        chunk_dur=300.0,
        cur_local_t=None,
    )
    assert ev_pts.new_local_t == 45.5
    assert ev_pts.progress_sec == 45.5

    ev_sc = parse_ffmpeg_line(
        "lavfi.scene_score=0.612",
        t_start=100.0,
        chunk_dur=300.0,
        cur_local_t=45.5,
    )
    assert len(ev_sc.visual_cuts) == 1
    assert ev_sc.visual_cuts[0].timestamp == 145.5
    assert ev_sc.visual_cuts[0].score == 0.612

    ev_out = parse_ffmpeg_line(
        "out_time_us=120000000",
        t_start=100.0,
        chunk_dur=300.0,
        cur_local_t=45.5,
    )
    assert ev_out.progress_sec == 120.0


def test_to_candidates_list() -> None:
    from rvcg.models import RawScanResult, VisualCut

    raw = RawScanResult(
        black_points=[12.5, 45.0],
        white_points=[30.0],
        visual_cuts=[VisualCut(timestamp=20.0, score=0.65), VisualCut(timestamp=50.0, score=0.45)],
    )
    candidates = raw.to_candidates_list()
    assert len(candidates) == 5
    timestamps = [c["timestamp"] for c in candidates]
    assert timestamps == [12.5, 20.0, 30.0, 45.0, 50.0]
    assert candidates[0]["kind"] == "black"
    assert candidates[1]["kind"] == "visual"
    assert candidates[2]["kind"] == "white"


def test_scan_keyframes_progress_and_sprites(tmp_path: Path) -> None:
    import subprocess

    from rvcg.models import BoundaryConfig
    from rvcg.scanner import scan_keyframes

    vid = tmp_path / "smoke.mp4"
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
            "testsrc=duration=4:size=320x180:rate=10",
            "-c:v",
            "libx264",
            "-g",
            "5",
            str(vid),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
    )

    phase_events: list[tuple[float, float, str]] = []

    def on_phase(phase: int, completed: float, total: float, info: str) -> None:
        if phase == 2:
            phase_events.append((completed, total, info))

    cfg = BoundaryConfig(workers=2)
    raw, sprite = scan_keyframes(
        vid,
        duration=4.0,
        config=cfg,
        out_dir=tmp_path,
        build_sprite=True,
        on_phase=on_phase,
    )

    assert len(phase_events) > 2
    # Progress must start at or near 0, not wait until the end
    assert phase_events[0][0] < 2.0
    assert sprite is not None
    assert (tmp_path / sprite.url).exists()
