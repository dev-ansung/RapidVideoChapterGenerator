import csv
import io
import json
import shutil
import subprocess
import sys
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


def _probe_video_geometry_and_audio(video_path: Path) -> tuple[int, int, bool]:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(video_path),
        ],
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(raw) if raw.strip() else {}
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    width, height = 1280, 720
    has_audio = False
    for st in streams:
        if not isinstance(st, dict):
            continue
        ctype = st.get("codec_type")
        if ctype == "video" and width == 1280 and height == 720:
            w = int(st.get("width") or 1280)
            h = int(st.get("height") or 720)
            width = max(2, w - (w % 2))
            height = max(2, h - (h % 2))
        elif ctype == "audio":
            has_audio = True
    return width, height, has_audio


def _probe_first_keyframe_at_or_after(video_path: Path, start_t: float, end_t: float) -> float:
    w_start = max(0.0, start_t - 0.5)
    w_end = max(w_start + 1.0, min(end_t, start_t + 18.0))
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-read_intervals",
            f"{w_start:.3f}%{w_end:.3f}",
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
    kfs: list[float] = []
    for line in raw.splitlines():
        val = safe_float(line.strip().rstrip(","))
        if val is not None and val >= start_t - 0.02 and val < end_t - 0.05:
            kfs.append(val)
    return min(kfs) if kfs else start_t


def _render_center_card_png(png_path: Path, title: str, start_t: float, end_t: float) -> None:
    ts_text = f"[{fmt_hms(start_t)} – {fmt_hms(end_t)}]"
    if sys.platform == "darwin" and shutil.which("swift"):
        meta_path = png_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(
                {
                    "title": title,
                    "ts_text": ts_text,
                    "out_path": str(png_path),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        swift_code = f"""
import Foundation
import AppKit

let width = 428
let height = 240
let data = try! Data(contentsOf: URL(fileURLWithPath: {json.dumps(str(meta_path))}))
let info = try! JSONSerialization.jsonObject(with: data) as! [String: String]
let titleText = info["title"]!
let tsText = info["ts_text"]!
let outPath = info["out_path"]!

let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.black.setFill()
NSRect(x: 0, y: 0, width: width, height: height).fill()

let paragraph = NSMutableParagraphStyle()
paragraph.alignment = .center
paragraph.lineSpacing = 4

let lines = titleText.components(separatedBy: "\\n")
let maxLineLen = lines.map {{ $0.count }}.max() ?? 10
let fontSize: CGFloat = maxLineLen > 20 ? 14.5 : (maxLineLen > 15 ? 16.5 : (titleText.count > 20 ? 18.0 : 21.0))
let titleFont = NSFont(name: "HiraginoSans-W6", size: fontSize) ?? NSFont.systemFont(ofSize: fontSize, weight: .semibold)
let tsFont = NSFont.monospacedDigitSystemFont(ofSize: 13, weight: .medium)

let fullAttr = NSMutableAttributedString()
fullAttr.append(NSAttributedString(string: titleText, attributes: [
    .font: titleFont,
    .foregroundColor: NSColor(white: 0.95, alpha: 1.0),
    .paragraphStyle: paragraph,
    .kern: 0.4
]))

let tsPara = NSMutableParagraphStyle()
tsPara.alignment = .center
tsPara.paragraphSpacingBefore = 10
fullAttr.append(NSAttributedString(string: "\\n" + tsText, attributes: [
    .font: tsFont,
    .foregroundColor: NSColor(white: 0.68, alpha: 1.0),
    .paragraphStyle: tsPara,
    .kern: 0.5
]))

let maxRect = NSRect(x: 12, y: 8, width: CGFloat(width - 24), height: CGFloat(height - 16))
let bound = fullAttr.boundingRect(with: maxRect.size, options: [.usesLineFragmentOrigin, .usesFontLeading])
let drawRect = NSRect(
    x: (CGFloat(width) - bound.width) / 2.0,
    y: (CGFloat(height) - bound.height) / 2.0,
    width: bound.width,
    height: bound.height
)
fullAttr.draw(with: drawRect, options: [.usesLineFragmentOrigin, .usesFontLeading])
NSGraphicsContext.restoreGraphicsState()

let pngData = rep.representation(using: .png, properties: [:])!
try! pngData.write(to: URL(fileURLWithPath: outPath))
"""
        try:
            subprocess.run(["swift", "-e", swift_code], stdin=subprocess.DEVNULL, check=True)
            return
        finally:
            meta_path.unlink(missing_ok=True)

    title_file = png_path.with_suffix(".title.txt")
    ts_file = png_path.with_suffix(".ts.txt")
    title_file.write_text(title, encoding="utf-8")
    ts_file.write_text(ts_text, encoding="utf-8")
    try:
        vf = (
            f"drawtext=textfile='{title_file}':fontcolor=white@0.95:fontsize=18:x=(w-text_w)/2:y=(h-text_h)/2-14,"
            f"drawtext=textfile='{ts_file}':fontcolor=white@0.68:fontsize=13:x=(w-text_w)/2:y=(h/2)+14"
        )
        res = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=428x240:d=1",
                "-vf",
                vf,
                "-frames:v",
                "1",
                "-update",
                "1",
                str(png_path),
            ],
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if res.returncode != 0 or not png_path.exists():
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
                    "color=c=black:s=428x240:d=1",
                    "-frames:v",
                    "1",
                    "-update",
                    "1",
                    str(png_path),
                ],
                stdin=subprocess.DEVNULL,
                check=True,
            )
    finally:
        title_file.unlink(missing_ok=True)
        ts_file.unlink(missing_ok=True)


def export_scene_cut(
    video_path: Path,
    segment: SceneSegment,
    output_path: Path | None = None,
) -> Path:
    src_path = video_path.expanduser().resolve()
    s_i = round(max(0.0, segment.start_time), 4)
    next_s = round(max(s_i + 0.5, segment.end_time), 4)
    card_dur = round(max(1.0, segment.card_dur), 4)

    slug = fmt_hms(s_i).replace(":", "-")
    if output_path is not None:
        out_mp4 = output_path.expanduser().resolve()
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = src_path.parent / f"{src_path.stem}_cuts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = out_dir / f"cut_{segment.id_str}_{slug}.mp4"

    src_w, src_h, has_audio = _probe_video_geometry_and_audio(src_path)
    kf_e = _probe_first_keyframe_at_or_after(src_path, s_i, next_s)
    bridge_dur = round(max(0.0, kf_e - s_i), 4)

    raw_cells = segment.cell_times if len(segment.cell_times) == 8 else compute_cell_times(s_i, next_s, card_dur)
    abs_starts = [round(max(s_i, min(max(s_i, next_s - 0.5), float(t))), 3) for t in raw_cells[:8]]

    with tempfile.TemporaryDirectory(prefix="rvcg_export_") as tmp_str:
        tmp_dir = Path(tmp_str)
        center_png = tmp_dir / "center_card.png"
        intro_mp4 = tmp_dir / "intro.mp4"
        body_mp4 = tmp_dir / "body.mp4"
        concat_txt = tmp_dir / "concat.txt"
        tmp_out = out_mp4.parent / f".{out_mp4.stem}.rvcg_tmp{out_mp4.suffix}"

        _render_center_card_png(center_png, segment.title, s_i, next_s)

        inputs: list[str] = []
        filter_parts: list[str] = []
        col_widths = [426, 428, 426, 426, 428, 426, 426, 428, 426]
        menlo_path = Path("/System/Library/Fonts/Menlo.ttc")
        font_opt = f"fontfile={menlo_path}:" if menlo_path.exists() else ""

        for idx_c, abs_st in enumerate(abs_starts):
            clip_dur = max(0.2, min(card_dur, next_s - abs_st))
            inputs += ["-ss", f"{abs_st:.3f}", "-t", f"{clip_dur:.4f}", "-i", str(src_path)]
            rel_st = round(card_dur + max(0.0, abs_st - s_i), 3)
            ts_expr = (
                f"%{{eif\\:trunc((t+{rel_st})/60)\\:d\\:2}}\\:"
                f"%{{eif\\:mod(trunc(t+{rel_st}),60)\\:d\\:2}}."
                f"%{{eif\\:mod(trunc((t+{rel_st})*1000),1000)\\:d\\:3}}"
            )
            grid_pos = idx_c if idx_c < 4 else idx_c + 1
            w = col_widths[grid_pos]
            filter_parts.append(
                f"[{idx_c}:v]fps=30000/1001,scale={w}:240,setsar=1/1,"
                f"drawtext={font_opt}text='{ts_expr}':x=8:y=h-th-6:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=6|8,"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=2,tpad=stop_mode=clone:stop_duration={card_dur:.4f},"
                f"trim=duration={card_dur:.4f},setpts=PTS-STARTPTS[cell{grid_pos}]"
            )

        inputs += [
            "-loop",
            "1",
            "-t",
            f"{card_dur:.4f}",
            "-r",
            "30000/1001",
            "-i",
            str(center_png),
            "-f",
            "lavfi",
            "-t",
            f"{card_dur:.4f}",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]

        filter_parts.append(
            "[8:v]fps=30000/1001,scale=428:240,setsar=1/1,format=yuv420p,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=2[cell4]"
        )

        stack_in = "".join(f"[cell{j}]" for j in range(9))
        layout = "0_0|426_0|854_0|0_240|426_240|854_240|0_480|426_480|854_480"
        scale_out = f",scale={src_w}:{src_h}" if (src_w, src_h) != (1280, 720) else ""
        filter_parts.append(f"{stack_in}xstack=inputs=9:layout={layout},format=yuv420p{scale_out},setsar=1/1[card_v]")

        if bridge_dur > 0.04 and has_audio:
            inputs += ["-ss", f"{s_i:.4f}", "-t", f"{bridge_dur:.4f}", "-i", str(src_path)]
            filter_parts.append(
                f"[10:v]fps=30000/1001,scale={src_w}:{src_h},format=yuv420p,setsar=1/1[br_v];"
                f"[10:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[br_a];"
                f"[card_v][9:a][br_v][br_a]concat=n=2:v=1:a=1[v][a]"
            )
            map_args = ["-map", "[v]", "-map", "[a]"]
        elif bridge_dur > 0.04:
            inputs += ["-ss", f"{s_i:.4f}", "-t", f"{bridge_dur:.4f}", "-i", str(src_path)]
            filter_parts.append(
                f"[10:v]fps=30000/1001,scale={src_w}:{src_h},format=yuv420p,setsar=1/1[br_v];"
                f"[card_v][br_v]concat=n=2:v=1:a=0[v]"
            )
            map_args = ["-map", "[v]"]
        elif has_audio:
            map_args = ["-map", "[card_v]", "-map", "9:a"]
        else:
            map_args = ["-map", "[card_v]"]

        audio_codec_args = ["-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2"] if has_audio else ["-an"]
        cmd_intro = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filter_parts),
            *map_args,
        ] + [
            "-c:v",
            "libx264",
            "-preset",
            "faster",
            "-crf",
            "25",
            "-profile:v",
            "high",
            "-level:v",
            "3.1",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-colorspace",
            "bt709",
            "-color_trc",
            "bt709",
            "-color_primaries",
            "bt709",
            "-x264-params",
            "ref=2:bframes=3:b-pyramid=normal:weightp=1:keyint=150:min-keyint=76:scenecut=0",
            "-video_track_timescale",
            "90000",
            *audio_codec_args,
            str(intro_mp4),
        ]
        subprocess.run(cmd_intro, stdin=subprocess.DEVNULL, check=True)

        cmd_body = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{kf_e + 0.001:.4f}",
            "-to",
            f"{next_s:.4f}",
            "-i",
            str(src_path),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(body_mp4),
        ]
        subprocess.run(cmd_body, stdin=subprocess.DEVNULL, check=True)

        concat_txt.write_text(f"file '{intro_mp4}'\nfile '{body_mp4}'\n", encoding="utf-8")
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-v",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_txt),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(tmp_out),
                ],
                stdin=subprocess.DEVNULL,
                check=True,
            )
            tmp_out.replace(out_mp4)
        except Exception:
            tmp_out.unlink(missing_ok=True)
            raise

    return out_mp4
