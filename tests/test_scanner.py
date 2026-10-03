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


def test_find_precision_transition(tmp_path: Path) -> None:
    import subprocess

    from rvcg.scanner import find_precision_transition

    vid = tmp_path / "scene_change.mp4"
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
            "color=c=red:s=320x180:d=2",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=2",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[out]",
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-g",
            "10",
            str(vid),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
    )

    # Next cut from t=0.5s should find the scene change around 2.0s
    res_next = find_precision_transition(vid, current_time=0.5, direction="next", threshold=0.20)
    assert res_next is not None
    assert 1.8 <= res_next.timestamp <= 2.2

    # Prev cut from t=3.0s should find the scene change around 2.0s
    res_prev = find_precision_transition(vid, current_time=3.0, direction="prev", threshold=0.20)
    assert res_prev is not None
    assert 1.8 <= res_prev.timestamp <= 2.2
