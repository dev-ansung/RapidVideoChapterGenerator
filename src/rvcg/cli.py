import argparse
import hashlib
import os
import re
import sys
import tempfile
import termios
import time
import unicodedata
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt

from rvcg.models import BoundaryConfig, SceneSegment, fmt_hms
from rvcg.muxer import embed_chapters_atomic, format_chapters_export
from rvcg.probe import extract_subtitles, probe_duration, probe_embedded_chapters
from rvcg.renderer import write_index_html
from rvcg.scanner import scan_keyframes
from rvcg.server import create_lifecycle_server, resolve_any_path
from rvcg.solver import segments_from_tuples, solve_boundaries

console = Console(stderr=True)


def parse_duration_sec(val: str | float | int) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    s = val.strip().lower()
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([smh]?)", s)
    if not m:
        raise ValueError(f"Invalid duration: {val}")
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "m":
        return num * 60.0
    if unit == "h":
        return num * 3600.0
    return num


def clean_input_path(raw: str) -> Path | None:
    resolved, kind = resolve_any_path(raw)
    return resolved if kind == "file" else None


def restore_tty() -> None:
    if not sys.stdin.isatty():
        return
    try:
        fd = sys.stdin.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[0] |= termios.ICRNL
        attrs[3] |= termios.ECHO | termios.ICANON | termios.ISIG
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
    except Exception:
        pass


def prompt_video_file(search_dir: Path | None = None) -> Path:
    restore_tty()
    base_dir = search_dir if search_dir is not None else Path.cwd()
    exts = {".mp4", ".mkv", ".mov", ".m4v", ".webm"}
    videos = sorted(
        (p for p in base_dir.iterdir() if p.is_file() and p.suffix.lower() in exts),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if videos:
        console.print(f"[bold cyan]Videos in {base_dir}:[/bold cyan]")
        for idx, vf in enumerate(videos, 1):
            size_mb = vf.stat().st_size / (1024 * 1024)
            disp_name = unicodedata.normalize("NFC", vf.name)
            console.print(f"  [bold yellow]{idx:2d}[/bold yellow]) {disp_name} [dim]({size_mb:.0f} MB)[/dim]")

    prompt_label = (
        "\n[bold yellow]?[/bold yellow] Select video #, drag & drop path, or [bold]q[/bold] to quit"
        if videos
        else "\n[bold yellow]?[/bold yellow] Enter/drag & drop video path, or [bold]q[/bold] to quit"
    )
    while True:
        try:
            restore_tty()
            raw = Prompt.ask(prompt_label, default="1" if videos else "", console=console)
        except (KeyboardInterrupt, EOFError):
            console.print()
            sys.exit(0)
        if not raw:
            continue
        val = raw.strip()
        if val.lower() in {"q", "quit", "exit"}:
            sys.exit(0)
        if val.isdigit() and 1 <= int(val) <= len(videos):
            return videos[int(val) - 1].resolve()
        candidate = clean_input_path(val)
        if candidate is not None:
            return candidate
        console.print("[bold red]Error:[/bold red] File not found. Enter a valid # or file path.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rapid-chapters",
        description="Rapid keyframe-accelerated video scene boundary detector and lossless chapter marker injector.",
    )
    parser.add_argument(
        "video",
        nargs="?",
        type=Path,
        default=None,
        help="Path to target video file (omit to launch Web Lifecycle Studio)",
    )
    parser.add_argument("-t", "--threshold", type=float, default=None, help="Visual cut sensitivity (0.0 to 1.0)")
    parser.add_argument(
        "-m", "--min-scene-len", type=str, default=None, help="Minimum duration between chapters (e.g. 180, 3m)"
    )
    parser.add_argument(
        "-M",
        "--max-scene-len",
        type=str,
        default=None,
        help="Maximum duration before smart subdivision (e.g. 600, 10m)",
    )
    parser.add_argument(
        "--target-scene-len",
        type=str,
        default=None,
        help="Target duration when subdividing long gaps (e.g. 360, 6m)",
    )
    parser.add_argument(
        "--preset",
        choices=["default", "podcast", "presentation", "action"],
        default="default",
        help="Predefined detection sensitivity profile",
    )
    parser.add_argument("-w", "--workers", type=int, default=8, help="Parallel FFmpeg keyframe worker count")
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="Destination file path (defaults to atomic in-place update)"
    )
    parser.add_argument(
        "-i",
        "--in-place",
        action="store_true",
        help="Inject chapter markers directly into input file (default for mp4 mode)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["mp4", "youtube", "ffmetadata", "json", "csv"],
        default="mp4",
        help="Output mode",
    )
    parser.add_argument("--title-template", type=str, default="Scene {n:02d}", help="Chapter naming template")
    parser.add_argument("--browse", action="store_true", help="Launch interactive 3x3 HTML5 scene browser")
    parser.add_argument("--ui", action="store_true", help="Launch Web Lifecycle Studio server")
    parser.add_argument(
        "--cli-prompt",
        action="store_true",
        help="Use interactive terminal prompt instead of Web Lifecycle Studio when no video is given",
    )
    parser.add_argument("--port", type=int, default=0, help="Port for Web Lifecycle Studio (default: auto)")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser window automatically")
    parser.add_argument(
        "--refresh", action="store_true", help="Force re-scan even if embedded chapters or cached browser exist"
    )
    return parser


def resolve_config(args: argparse.Namespace) -> BoundaryConfig:
    cfg = BoundaryConfig.from_preset(str(args.preset))
    if args.threshold is not None:
        cfg = replace(cfg, scene_threshold=float(args.threshold))
    if args.min_scene_len is not None:
        cfg = replace(cfg, min_seg=parse_duration_sec(str(args.min_scene_len)))
    if args.max_scene_len is not None:
        cfg = replace(cfg, max_seg=parse_duration_sec(str(args.max_scene_len)))
    if args.target_scene_len is not None:
        cfg = replace(cfg, target_seg=parse_duration_sec(str(args.target_scene_len)))
    cfg = replace(
        cfg,
        workers=max(1, int(args.workers)),
        title_template=str(args.title_template),
    )
    return cfg


def process_video(
    video_path: Path,
    args: argparse.Namespace,
    config: BoundaryConfig,
    interactive: bool,
) -> None:
    resolved_vid = clean_input_path(str(video_path))
    if resolved_vid is None:
        console.print(f"[bold red]Error:[/bold red] File not found: {video_path}")
        return
    video_path = resolved_vid

    t0 = time.perf_counter()
    duration = probe_duration(video_path)
    out_fmt = str(args.format)
    want_browse = bool(args.browse)
    should_refresh = bool(args.refresh)

    stat = video_path.stat()
    digest = hashlib.sha1(f"{video_path}:{stat.st_size}:{int(stat.st_mtime)}".encode("utf-8")).hexdigest()[:12]
    browser_dir = Path(tempfile.gettempdir()) / f"rvcg_browser_{digest}"
    index_html = browser_dir / "index.html"
    disp_name = unicodedata.normalize("NFC", video_path.name)

    existing_chapters = [] if should_refresh else probe_embedded_chapters(video_path)
    if len(existing_chapters) >= 3 and interactive and not should_refresh:
        try:
            restore_tty()
            should_refresh = Confirm.ask(
                f"[bold yellow]?[/bold yellow] [cyan]{disp_name}[/cyan] already has {len(existing_chapters)} chapters. Re-detect?",
                default=False,
                console=console,
            )
            if should_refresh:
                existing_chapters = []
        except (KeyboardInterrupt, EOFError):
            console.print()
            sys.exit(0)

    if want_browse and index_html.exists() and not should_refresh and len(existing_chapters) >= 3:
        console.print(f"[dim]Using cached browser in {browser_dir}[/dim]")
        if not args.no_open:
            webbrowser.open(index_html.as_uri())
        return

    console.print(f"[bold cyan]Video:[/bold cyan] {disp_name} ([bold]{fmt_hms(duration)}[/bold])")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description:<32}"),
        BarColumn(bar_width=28),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TextColumn("[cyan]{task.fields[info]}"),
        console=console,
    ) as progress:
        phase_tasks: dict[int, TaskID] = {
            1: progress.add_task("[1/5] Embedded chapter check", total=1.0, info="waiting..."),
            2: progress.add_task("[2/5] Keyframe visual scan", total=duration, info="waiting..."),
            3: progress.add_task("[3/5] Priority anchor placement", total=1.0, info="waiting..."),
            4: progress.add_task("[4/5] Long-segment subdivision", total=1.0, info="waiting..."),
            5: progress.add_task("[5/5] Tail merge & chapter mux", total=1.0, info="waiting..."),
        }
        t_spr: TaskID | None = (
            progress.add_task("      Timeline sprite sheet", total=duration, info="rendering...")
            if want_browse
            else None
        )

        def handle_phase(phase: int, completed: float, total: float, info: str) -> None:
            tid = phase_tasks.get(phase)
            if tid is not None:
                progress.update(tid, completed=completed, total=total, info=info)

        def handle_sprite(completed: float) -> None:
            if t_spr is not None:
                progress.update(t_spr, completed=completed)

        use_existing = len(existing_chapters) >= 3
        if use_existing:
            handle_phase(1, 1.0, 1.0, f"{len(existing_chapters)} embedded chapters found")
            handle_phase(2, duration, duration, "skipped (chapters found)")
            handle_phase(3, 1.0, 1.0, "skipped (chapters found)")
            handle_phase(4, 1.0, 1.0, "skipped (chapters found)")
            segments: list[SceneSegment] = segments_from_tuples(existing_chapters, config.card_dur)
            handle_phase(5, 1.0, 1.0, f"{len(segments)} chapters ready")
        else:
            handle_phase(1, 1.0, 1.0, f"0 chapters ({config.workers}-worker keyframe scan)")
            handle_phase(2, 0.0, duration, "0 black fades · 0 visual cuts")
            segments = []

        if want_browse:
            browser_dir.mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=2) as ex:
                scan_fut = ex.submit(
                    scan_keyframes,
                    video_path,
                    duration,
                    config,
                    browser_dir,
                    True,
                    use_existing,
                    handle_phase,
                    handle_sprite,
                )
                sub_fut = ex.submit(extract_subtitles, video_path, browser_dir)
                raw_scan, sprite_meta = scan_fut.result()
                sub_tracks = sub_fut.result()
            if not use_existing:
                segments = solve_boundaries(duration, raw_scan, config, handle_phase)
            if t_spr is not None and sprite_meta is not None:
                progress.update(
                    t_spr,
                    completed=duration,
                    info=f"{sprite_meta.total_frames} frames (1/{sprite_meta.interval}s)",
                )
        else:
            sprite_meta = None
            sub_tracks = []
            if not use_existing:
                raw_scan, _ = scan_keyframes(
                    video_path=video_path,
                    duration=duration,
                    config=config,
                    out_dir=None,
                    build_sprite=False,
                    skip_boundary_scan=False,
                    on_phase=handle_phase,
                    on_sprite=None,
                )
                segments = solve_boundaries(duration, raw_scan, config, handle_phase)

        target_video = video_path
        if out_fmt == "mp4" and (not use_existing or args.output is not None):
            handle_phase(5, 0.5, 1.0, f"muxing {len(segments)} chapters (-c copy)...")
            target_video = embed_chapters_atomic(video_path, segments, args.output)
            handle_phase(5, 1.0, 1.0, f"{len(segments)} chapters embedded -> {target_video.name}")

    if out_fmt != "mp4":
        rendered_text = format_chapters_export(segments, out_fmt)
        if args.output is not None:
            out_file = args.output.expanduser().resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(rendered_text, encoding="utf-8")
            console.print(f"[bold green]✓ Wrote {len(segments)} chapters ({out_fmt}) -> {out_file}[/bold green]")
        else:
            sys.stdout.write(rendered_text)
            sys.stdout.flush()
        return

    elapsed = time.perf_counter() - t0
    if want_browse and sprite_meta is not None:
        safe_link_name = f"video{target_video.suffix.lower()}"
        video_link = browser_dir / safe_link_name
        if video_link.exists() or video_link.is_symlink():
            video_link.unlink()
        video_link.symlink_to(target_video)
        write_index_html(
            browser_dir,
            unicodedata.normalize("NFC", target_video.stem),
            safe_link_name,
            segments,
            sprite_meta,
            sub_tracks,
        )
        console.print(
            f"[bold green]✓ Ready in {elapsed:.1f}s![/bold green] "
            f"{len(segments)} chapters embedded · {sprite_meta.total_frames} sprite frames -> {index_html}"
        )
        if not args.no_open:
            webbrowser.open(index_html.as_uri())
    else:
        console.print(
            f"[bold green]✓ Ready in {elapsed:.1f}s![/bold green] "
            f"{len(segments)} chapters embedded losslessly -> {target_video}"
        )


def run_web_studio(
    default_dir: Path, config: BoundaryConfig, initial_video: Path | None, port: int, no_open: bool
) -> None:
    server = create_lifecycle_server(
        default_dir=default_dir,
        default_config=config,
        initial_video=initial_video,
        port=port,
    )
    raw_host = server.server_address[0]
    host = raw_host.decode("utf-8") if isinstance(raw_host, (bytes, bytearray)) else raw_host
    bound_port = int(server.server_address[1])
    url = f"http://{host}:{bound_port}/"
    console.print(
        f"[bold green]✓ Web Lifecycle Studio running at[/bold green] [bold cyan]{url}[/bold cyan] [dim](Ctrl+C to stop)[/dim]"
    )
    if not no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Shutting down Web Lifecycle Studio...[/dim]")
    finally:
        server.server_close()


def main(argv: Sequence[str] | None = None) -> None:
    os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")
    parser = build_parser()
    args = parser.parse_args(argv)
    config = resolve_config(args)

    if args.ui or (args.video is None and not args.cli_prompt):
        init_vid = clean_input_path(str(args.video)) if args.video is not None else None
        base_dir = init_vid.parent if init_vid is not None else Path.cwd()
        run_web_studio(base_dir, config, init_vid, int(args.port), bool(args.no_open))
        return

    if args.video is not None:
        process_video(args.video.expanduser(), args, config, interactive=False)
        if not sys.stdin.isatty() or args.format != "mp4" or not args.cli_prompt:
            return
        console.print()

    while True:
        video_path = prompt_video_file()
        process_video(video_path, args, config, interactive=True)
        console.print()


if __name__ == "__main__":
    main()
