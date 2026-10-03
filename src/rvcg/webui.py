import json
from pathlib import Path

from rvcg.models import BoundaryConfig

STATIC_DIR = Path(__file__).parent / "static"


def render_webui_html(default_dir: str, default_config: BoundaryConfig, initial_video: str | None = None) -> str:
    template = (STATIC_DIR / "webui.html").read_text(encoding="utf-8")
    cfg_json = json.dumps(
        {
            "min_seg": default_config.min_seg,
            "max_seg": default_config.max_seg,
            "target_seg": default_config.target_seg,
            "workers": default_config.workers,
            "threshold": default_config.scene_threshold,
            "title_template": default_config.title_template,
        },
        ensure_ascii=False,
    )
    return (
        template.replace("__DEFAULT_CFG__", cfg_json)
        .replace("__INIT_DIR__", json.dumps(default_dir, ensure_ascii=False))
        .replace("__INIT_VID__", json.dumps(initial_video, ensure_ascii=False))
    )
