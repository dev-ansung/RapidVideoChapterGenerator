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
    )
    assert ev_black.black_midpoints == [111.0]

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
