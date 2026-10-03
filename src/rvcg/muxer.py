import csv
import io
import json
import subprocess
import tempfile
from pathlib import Path

from rvcg.models import SceneSegment, fmt_hms


def escape_ffmetadata(val: str) -> str:
    out = val.replace("\\", "\\\\")
    for ch in ("=", ";", "#"):
        out = out.replace(ch, f"\\{ch}")
    return out.replace("\n", "\\\n")


def build_ffmetadata(segments: list[SceneSegment]) -> str:
    lines = [";FFMETADATA1"]
    for seg in segments:
        start_ms = max(0, int(round(seg.start_time * 1000)))
        end_ms = max(start_ms + 1, int(round(seg.end_time * 1000)))
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={escape_ffmetadata(seg.title)}",
            ]
        )
    return "\n".join(lines) + "\n"


def format_chapters_export(segments: list[SceneSegment], fmt: str) -> str:
    if fmt == "youtube":
        return "\n".join(f"{fmt_hms(seg.start_time)} - {seg.title}" for seg in segments) + "\n"
    if fmt == "ffmetadata":
        return build_ffmetadata(segments)
    if fmt == "json":
        return json.dumps([seg.to_dict() for seg in segments], indent=2, ensure_ascii=False) + "\n"
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["index", "start_time", "end_time", "title"])
        for seg in segments:
            writer.writerow([seg.index, f"{seg.start_time:.2f}", f"{seg.end_time:.2f}", seg.title])
        return buf.getvalue()
    raise ValueError(f"Unsupported format: {fmt}")


def embed_chapters_atomic(
    video_path: Path,
    segments: list[SceneSegment],
    output_path: Path | None = None,
) -> Path:
    dest_path = output_path.expanduser().resolve() if output_path is not None else video_path.resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_video = dest_path.parent / f".{dest_path.stem}.rvcg_tmp{dest_path.suffix}"

    with tempfile.NamedTemporaryFile("w", suffix=".ffmeta", encoding="utf-8", delete=False) as mf:
        mf.write(build_ffmetadata(segments))
        meta_path = Path(mf.name)

    try:
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-i",
            str(video_path),
            "-i",
            str(meta_path),
            "-map",
            "0",
            "-map_metadata",
            "1",
            "-map_chapters",
            "1",
            "-c",
            "copy",
        ]
        if dest_path.suffix.lower() in {".mp4", ".m4v", ".mov"}:
            cmd.extend(["-movflags", "+faststart"])
        cmd.append(str(tmp_video))

        subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True)
        if not tmp_video.exists() or tmp_video.stat().st_size == 0:
            raise RuntimeError("Remuxed output file is empty")
        tmp_video.replace(dest_path)
        return dest_path
    except Exception:
        tmp_video.unlink(missing_ok=True)
        raise
    finally:
        meta_path.unlink(missing_ok=True)
