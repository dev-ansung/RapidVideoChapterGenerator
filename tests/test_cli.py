from pathlib import Path

from rvcg.cli import build_parser, clean_input_path, parse_duration_sec, resolve_config


def test_parse_duration_sec() -> None:
    assert parse_duration_sec("180") == 180.0
    assert parse_duration_sec("45s") == 45.0
    assert parse_duration_sec("3m") == 180.0
    assert parse_duration_sec("1.5h") == 5400.0


def test_clean_input_path(tmp_path: Path) -> None:
    f = tmp_path / "my video.mp4"
    f.write_bytes(b"00")
    escaped = str(f).replace(" ", r"\ ")
    assert clean_input_path(escaped) == f.resolve()
    assert clean_input_path(f"'{f}'") == f.resolve()
    assert clean_input_path("/nonexistent/file.mp4") is None


def test_cli_parser_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "video.mp4",
            "-m",
            "2m",
            "--threshold",
            "0.42",
            "--black-min-dur",
            "0.6",
            "--black-only",
            "--format",
            "youtube",
            "--browse",
        ]
    )
    assert args.min_scene_len == "2m"
    assert args.threshold == 0.42
    assert args.black_min_dur == 0.6
    assert args.black_only is True
    assert args.format == "youtube"
    assert args.browse is True

    cfg = resolve_config(args)
    assert cfg.min_seg == 120.0
    assert cfg.black_min_dur == 0.6
    assert cfg.enable_black_fades is True
    assert cfg.enable_visual_cuts is False
    assert cfg.enable_subdivide is False
