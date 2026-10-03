import html
import json
from pathlib import Path

from rvcg.models import SceneSegment, SpriteMeta, SubtitleTrack

STATIC_DIR = Path(__file__).parent / "static"


def write_index_html(
    out_dir: Path,
    video_title: str,
    video_src_rel: str,
    segments: list[SceneSegment],
    sprite_meta: SpriteMeta,
    sub_tracks: list[SubtitleTrack],
) -> Path:
    template = (STATIC_DIR / "browser.html").read_text(encoding="utf-8")
    items = [s.to_dict() for s in segments]
    sprite = sprite_meta.to_dict()
    subs = [t.to_dict() for t in sub_tracks]

    rendered = (
        template.replace("__VIDEO_TITLE__", html.escape(video_title))
        .replace("__VIDEO_SRC__", json.dumps(video_src_rel, ensure_ascii=False))
        .replace("__SPRITE__", json.dumps(sprite, ensure_ascii=False))
        .replace("__CUTS__", json.dumps(items, ensure_ascii=False))
        .replace("__SUBTITLES__", json.dumps(subs, ensure_ascii=False))
    )
    index_path = out_dir / "index.html"
    index_path.write_text(rendered, encoding="utf-8")
    return index_path
