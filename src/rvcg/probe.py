import json
import subprocess
from pathlib import Path

from rvcg.models import SubtitleTrack


def probe_duration(video_path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        stdin=subprocess.DEVNULL,
        text=True,
    ).strip()
    return float(out)


def probe_embedded_chapters(video_path: Path, min_chapter_sec: float = 15.0) -> list[tuple[float, float, str]]:
    chapters_raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_chapters",
            "-of",
            "json",
            str(video_path),
        ],
        stdin=subprocess.DEVNULL,
        text=True,
    )
    payload = json.loads(chapters_raw)
    chapters = payload.get("chapters", []) if isinstance(payload, dict) else []
    chapter_segs: list[tuple[float, float, str]] = []
    for idx, ch in enumerate(chapters, 1):
        if not isinstance(ch, dict):
            continue
        s = float(ch.get("start_time", 0.0))
        e = float(ch.get("end_time", 0.0))
        tags = ch.get("tags")
        raw_title = tags.get("title") if isinstance(tags, dict) else None
        title = str(raw_title) if raw_title else f"Scene {idx:02d}"
        if e - s >= min_chapter_sec:
            chapter_segs.append((s, e, title))
    return chapter_segs


def extract_subtitles(video_path: Path, out_dir: Path) -> list[SubtitleTrack]:
    tracks: list[SubtitleTrack] = []

    for ext in [".srt", ".SRT", ".vtt", ".VTT"]:
        sidecar = video_path.with_suffix(ext)
        if sidecar.exists() and sidecar.stat().st_size > 0:
            vtt_path = out_dir / "sub_external.vtt"
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(sidecar), "-f", "webvtt", str(vtt_path)],
                stdin=subprocess.DEVNULL,
                check=False,
            )
            if vtt_path.exists() and vtt_path.stat().st_size > 0:
                tracks.append(
                    SubtitleTrack(
                        label="External SRT",
                        srclang="zh",
                        vtt=vtt_path.read_text(encoding="utf-8", errors="replace"),
                        default=True,
                    )
                )
            break

    probe_raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index,codec_name:stream_tags=language,title",
            "-of",
            "json",
            str(video_path),
        ],
        stdin=subprocess.DEVNULL,
        text=True,
    )
    payload = json.loads(probe_raw)
    sub_streams = payload.get("streams", []) if isinstance(payload, dict) else []
    text_codecs = {"subrip", "srt", "mov_text", "ass", "ssa", "webvtt", "text"}

    for s_idx, st in enumerate(sub_streams):
        if not isinstance(st, dict):
            continue
        codec = str(st.get("codec_name", ""))
        if codec and codec not in text_codecs:
            continue
        tags = st.get("tags")
        lang = str(tags.get("language", "und")) if isinstance(tags, dict) else "und"
        raw_title = tags.get("title") if isinstance(tags, dict) else None
        title = str(raw_title) if raw_title else f"Embedded #{s_idx + 1} ({lang})"
        vtt_path = out_dir / f"sub_emb_{s_idx}.vtt"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-i",
                str(video_path),
                "-map",
                f"0:s:{s_idx}",
                "-f",
                "webvtt",
                str(vtt_path),
            ],
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if vtt_path.exists() and vtt_path.stat().st_size > 0:
            tracks.append(
                SubtitleTrack(
                    label=title,
                    srclang=lang,
                    vtt=vtt_path.read_text(encoding="utf-8", errors="replace"),
                    default=len(tracks) == 0,
                )
            )
    return tracks
