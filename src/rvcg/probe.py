import json
import re
import subprocess
import unicodedata
from pathlib import Path

from rvcg.models import SubtitleTrack


def safe_float(val: str | int | float | None) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = val.strip()
    if not s or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_duration_tag(val: str | int | float | None) -> float | None:
    direct = safe_float(val)
    if direct is not None:
        return direct if direct > 0 else None
    if not isinstance(val, str):
        return None
    m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)", val.strip())
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    ss = float(m.group(3))
    tot = hh * 3600.0 + mm * 60.0 + ss
    return tot if tot > 0 else None


def probe_duration(video_path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags=DURATION:stream=duration:stream_tags=DURATION",
            "-of",
            "json",
            str(video_path),
        ],
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    ).strip()

    candidates: list[float] = []
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = safe_float(raw)
            if isinstance(payload, float) and payload > 0:
                return payload
            payload = {}

        if isinstance(payload, dict):
            fmt = payload.get("format")
            if isinstance(fmt, dict):
                d_fmt = parse_duration_tag(fmt.get("duration"))
                if d_fmt is not None:
                    candidates.append(d_fmt)
                f_tags = fmt.get("tags")
                if isinstance(f_tags, dict):
                    for k, v in f_tags.items():
                        if str(k).upper().startswith("DURATION"):
                            dt = parse_duration_tag(v)
                            if dt is not None:
                                candidates.append(dt)

            streams = payload.get("streams")
            if isinstance(streams, list):
                for st in streams:
                    if not isinstance(st, dict):
                        continue
                    d_st = parse_duration_tag(st.get("duration"))
                    if d_st is not None:
                        candidates.append(d_st)
                    s_tags = st.get("tags")
                    if isinstance(s_tags, dict):
                        for k, v in s_tags.items():
                            if str(k).upper().startswith("DURATION"):
                                dt = parse_duration_tag(v)
                                if dt is not None:
                                    candidates.append(dt)

    if candidates:
        return max(candidates)

    pkt_raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-skip_frame",
            "nokey",
            "-show_entries",
            "packet=pts_time",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    for line in reversed(pkt_raw.splitlines()):
        val = safe_float(line.strip().rstrip(","))
        if val is not None and val > 0:
            return val

    raise RuntimeError(f"Cannot determine duration for '{video_path.name}' (corrupt or incomplete video container)")


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
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(chapters_raw)
    chapters = payload.get("chapters", []) if isinstance(payload, dict) else []
    chapter_segs: list[tuple[float, float, str]] = []
    for idx, ch in enumerate(chapters, 1):
        if not isinstance(ch, dict):
            continue
        s = safe_float(ch.get("start_time"))
        e = safe_float(ch.get("end_time"))
        if s is None or e is None:
            continue
        tags = ch.get("tags")
        raw_title = tags.get("title") if isinstance(tags, dict) else None
        title = unicodedata.normalize("NFC", str(raw_title)) if raw_title else f"Scene {idx:02d}"
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
        encoding="utf-8",
        errors="replace",
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
        title = unicodedata.normalize("NFC", str(raw_title)) if raw_title else f"Embedded #{s_idx + 1} ({lang})"
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
