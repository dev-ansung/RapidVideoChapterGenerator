from pathlib import Path

from rvcg import __version__
from rvcg.models import SpriteMeta
from rvcg.renderer import write_index_html


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_browser_template_pip_guard(tmp_path: Path) -> None:
    out_html = write_index_html(
        out_dir=tmp_path,
        video_title="Demo",
        video_src_rel="demo.mp4",
        segments=[],
        sprite_meta=SpriteMeta(url="sprite.jpg", interval=10, cols=10, rows=1, total_frames=1),
        sub_tracks=[],
    )
    content = out_html.read_text(encoding="utf-8")
    assert "function isInPip()" in content
    assert "if (!isInPip())" in content
