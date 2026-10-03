import subprocess
from pathlib import Path

from rvcg.models import SceneSegment
from rvcg.muxer import build_ffmetadata, embed_chapters_atomic, export_scene_cut, format_chapters_export
from rvcg.probe import probe_duration, probe_embedded_chapters


def _sample_segments() -> list[SceneSegment]:
    return [
        SceneSegment(
            index=1,
            start_time=0.0,
            end_time=2.0,
            title="Intro: Part = 1; #A",
            cell_times=[0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6],
        ),
        SceneSegment(
            index=2,
            start_time=2.0,
            end_time=4.0,
            title="Scene 02",
            cell_times=[2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6],
        ),
    ]


def test_build_ffmetadata_escapes_special_chars() -> None:
    meta = build_ffmetadata(_sample_segments())
    assert meta.startswith(";FFMETADATA1\n")
    assert "START=0\nEND=2000\ntitle=Intro: Part \\= 1\\; \\#A\n" in meta
    assert "START=2000\nEND=4000\ntitle=Scene 02\n" in meta


def test_format_chapters_export_modes() -> None:
    segs = _sample_segments()
    yt = format_chapters_export(segs, "youtube")
    assert "00:00:00 - Intro: Part = 1; #A" in yt
    assert "00:00:02 - Scene 02" in yt

    csv_out = format_chapters_export(segs, "csv")
    assert "index,start_time,end_time,title" in csv_out

    json_out = format_chapters_export(segs, "json")
    assert '"scene_number": 1' in json_out


def test_embed_chapters_atomic_roundtrip(tmp_path: Path) -> None:
    vid = tmp_path / "sample.mp4"
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
            "color=c=black:s=320x180:d=4",
            "-c:v",
            "libx264",
            "-g",
            "15",
            str(vid),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
    )
    segs = _sample_segments()
    out_path = embed_chapters_atomic(vid, segs, output_path=None)
    assert out_path == vid
    chapters = probe_embedded_chapters(vid, min_chapter_sec=0.5)
    assert len(chapters) == 2
    assert chapters[0][2] == "Intro: Part = 1; #A"
    assert chapters[1][2] == "Scene 02"


def test_export_scene_cut_creates_valid_video(tmp_path: Path) -> None:
    vid = tmp_path / "movie.mp4"
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
            "color=c=navy:s=320x180:d=4",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100:d=4",
            "-c:v",
            "libx264",
            "-g",
            "15",
            "-c:a",
            "aac",
            "-shortest",
            str(vid),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
    )
    seg = SceneSegment(
        index=1,
        start_time=0.0,
        end_time=4.0,
        title="Scene 01",
        cell_times=[0.2, 0.6, 1.0, 1.4, 1.8, 2.2, 2.6, 3.0],
        card_dur=1.5,
    )
    out_file = export_scene_cut(vid, seg)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    assert out_file.parent.name == "movie_cuts"
    assert out_file.name == "cut_01_00-00-00.mp4"
    dur = probe_duration(out_file)
    assert dur >= 4.5
