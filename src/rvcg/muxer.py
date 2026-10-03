import csv
import io
import json
import subprocess
import tempfile
from pathlib import Path

from rvcg.models import SceneSegment, fmt_hms
from rvcg.probe import safe_float
from rvcg.solver import compute_cell_times


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
            "ffmpeg", "-nostdin", "-y", "-v", "error",
            "-i", str(video_path), "-i", str(meta_path),
            "-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy",
        ]  # fmt: skip
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


def export_scene_cut(video_path: Path, segment: SceneSegment, output_path: Path | None = None) -> Path:
    src_path = video_path.expanduser().resolve()
    s_i = round(max(0.0, segment.start_time), 4)
    next_s = round(max(s_i + 0.5, segment.end_time), 4)
    card_dur = round(max(1.0, segment.card_dur), 4)

    slug = fmt_hms(s_i).replace(":", "-")
    out_mp4 = (
        output_path.expanduser().resolve()
        if output_path is not None
        else src_path.parent / f"{src_path.stem}_cuts" / f"cut_{segment.id_str}_{slug}.mp4"
    )
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    probe_cmd = [
        "ffprobe", "-v", "error", "-read_intervals", f"{max(0.0, s_i - 0.5):.3f}%{min(next_s, s_i + 18.0):.3f}",
        "-show_entries", "stream=codec_type,width,height:packet=pts_time", "-skip_frame", "nokey", "-of", "json",
        str(src_path),
    ]  # fmt: skip
    probe = json.loads(
        subprocess.check_output(probe_cmd, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace") or "{}"
    )
    v_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    has_audio = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
    src_w = max(2, int(v_streams[0].get("width", 1280)) & ~1) if v_streams else 1280
    src_h = max(2, int(v_streams[0].get("height", 720)) & ~1) if v_streams else 720
    kfs = [
        t
        for p in probe.get("packets", [])
        if (t := safe_float(p.get("pts_time"))) is not None and s_i - 0.02 <= t < next_s - 0.05
    ]
    kf_e = min(kfs) if kfs else s_i
    bridge_dur = round(max(0.0, kf_e - s_i), 4)

    cells = segment.cell_times if len(segment.cell_times) == 8 else compute_cell_times(s_i, next_s, card_dur)
    abs_starts = [round(max(s_i, min(max(s_i, next_s - 0.5), float(t))), 3) for t in cells[:8]]

    with tempfile.TemporaryDirectory(prefix="rvcg_export_") as tmp_str:
        tmp_dir = Path(tmp_str)
        title_txt, ts_txt = tmp_dir / "title.txt", tmp_dir / "ts.txt"
        intro_mp4, body_mp4, concat_txt = tmp_dir / "intro.mp4", tmp_dir / "body.mp4", tmp_dir / "concat.txt"
        tmp_out = out_mp4.parent / f".{out_mp4.stem}.rvcg_tmp{out_mp4.suffix}"

        title_txt.write_text(segment.title, encoding="utf-8")
        ts_txt.write_text(f"[{fmt_hms(s_i)} – {fmt_hms(next_s)}]", encoding="utf-8")

        menlo = Path("/System/Library/Fonts/Menlo.ttc")
        hiragino = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
        mono_font = f"fontfile='{menlo}':" if menlo.exists() else ""
        title_font = f"fontfile='{hiragino}':" if hiragino.exists() else mono_font

        inputs: list[str] = []
        filter_parts: list[str] = []
        col_widths = [426, 428, 426, 426, 428, 426, 426, 428, 426]

        for idx_c, abs_st in enumerate(abs_starts):
            clip_dur = max(0.2, min(card_dur, next_s - abs_st))
            inputs += ["-ss", f"{abs_st:.3f}", "-t", f"{clip_dur:.4f}", "-i", str(src_path)]
            rel_st = round(card_dur + max(0.0, abs_st - s_i), 3)
            ts_expr = (
                f"%{{eif\\:trunc((t+{rel_st})/60)\\:d\\:2}}\\:"
                f"%{{eif\\:mod(trunc(t+{rel_st}),60)\\:d\\:2}}."
                f"%{{eif\\:mod(trunc((t+{rel_st})*1000),1000)\\:d\\:3}}"
            )
            pos = idx_c if idx_c < 4 else idx_c + 1
            filter_parts.append(
                f"[{idx_c}:v]fps=30000/1001,scale={col_widths[pos]}:240,setsar=1/1,"
                f"drawtext={mono_font}text='{ts_expr}':x=8:y=h-th-6:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=6|8,"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=2,tpad=stop_mode=clone:stop_duration={card_dur:.4f},"
                f"trim=duration={card_dur:.4f},setpts=PTS-STARTPTS[cell{pos}]"
            )

        inputs += ["-f", "lavfi", "-t", f"{card_dur:.4f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        filter_parts.append(
            f"color=c=black:s=428x240:r=30000/1001:d={card_dur:.4f},setsar=1/1,"
            f"drawtext={title_font}textfile='{title_txt}':fontcolor=white@0.95:fontsize=18:x=(w-text_w)/2:y=(h-text_h)/2-14,"
            f"drawtext={mono_font}textfile='{ts_txt}':fontcolor=white@0.68:fontsize=13:x=(w-text_w)/2:y=(h/2)+14,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=2[cell4]"
        )

        stack_in = "".join(f"[cell{j}]" for j in range(9))
        layout = "0_0|426_0|854_0|0_240|426_240|854_240|0_480|426_480|854_480"
        scale_out = f",scale={src_w}:{src_h}" if (src_w, src_h) != (1280, 720) else ""
        filter_parts.append(f"{stack_in}xstack=inputs=9:layout={layout},format=yuv420p{scale_out},setsar=1/1[card_v]")

        if bridge_dur > 0.04:
            inputs += ["-ss", f"{s_i:.4f}", "-t", f"{bridge_dur:.4f}", "-i", str(src_path)]
            filter_parts.append(f"[9:v]fps=30000/1001,scale={src_w}:{src_h},format=yuv420p,setsar=1/1[br_v]")
            if has_audio:
                filter_parts.append(
                    "[9:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[br_a];"
                    "[card_v][8:a][br_v][br_a]concat=n=2:v=1:a=1[v][a]"
                )
                map_args = ["-map", "[v]", "-map", "[a]"]
            else:
                filter_parts.append("[card_v][br_v]concat=n=2:v=1:a=0[v]")
                map_args = ["-map", "[v]"]
        else:
            map_args = ["-map", "[card_v]", "-map", "8:a"] if has_audio else ["-map", "[card_v]"]

        aud_args = ["-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2"] if has_audio else ["-an"]
        cmd_intro = [
            "ffmpeg", "-nostdin", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filter_parts), *map_args,
            "-c:v", "libx264", "-preset", "faster", "-crf", "25", "-profile:v", "high", "-level:v", "3.1",
            "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709",
            "-color_primaries", "bt709", "-video_track_timescale", "90000", *aud_args, str(intro_mp4),
        ]  # fmt: skip
        subprocess.run(cmd_intro, stdin=subprocess.DEVNULL, check=True)

        cmd_body = [
            "ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{kf_e + 0.001:.4f}", "-to", f"{next_s:.4f}",
            "-i", str(src_path), "-c", "copy", "-avoid_negative_ts", "make_zero", str(body_mp4),
        ]  # fmt: skip
        subprocess.run(cmd_body, stdin=subprocess.DEVNULL, check=True)

        concat_txt.write_text(f"file '{intro_mp4}'\nfile '{body_mp4}'\n", encoding="utf-8")
        try:
            cmd_concat = [
                "ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat_txt), "-c", "copy", "-movflags", "+faststart", str(tmp_out),
            ]  # fmt: skip
            subprocess.run(cmd_concat, stdin=subprocess.DEVNULL, check=True)
            tmp_out.replace(out_mp4)
        except Exception:
            tmp_out.unlink(missing_ok=True)
            raise

    return out_mp4
