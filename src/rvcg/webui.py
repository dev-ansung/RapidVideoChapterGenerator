import json
from pathlib import Path

from rvcg.models import PRESETS, BoundaryConfig

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
            "black_min_dur": default_config.black_min_dur,
            "black_pic_th": default_config.black_pic_th,
            "white_pic_th": default_config.white_pic_th,
            "black_pix_th": default_config.black_pix_th,
            "white_pix_th": default_config.white_pix_th,
            "enable_black_fades": default_config.enable_black_fades,
            "enable_white_fades": default_config.enable_white_fades,
            "enable_visual_cuts": default_config.enable_visual_cuts,
            "enable_subdivide": default_config.enable_subdivide,
            "card_dur": default_config.card_dur,
            "title_template": default_config.title_template,
        },
        ensure_ascii=False,
    )
    presets_json = json.dumps(
        {
            k: {
                "id": v.id,
                "name": v.name,
                "description": v.description,
                "config": {
                    "min_seg": v.config.min_seg,
                    "max_seg": v.config.max_seg,
                    "target_seg": v.config.target_seg,
                    "scene_threshold": v.config.scene_threshold,
                    "black_min_dur": v.config.black_min_dur,
                    "black_pic_th": v.config.black_pic_th,
                    "white_pic_th": v.config.white_pic_th,
                    "black_pix_th": v.config.black_pix_th,
                    "white_pix_th": v.config.white_pix_th,
                    "enable_black_fades": v.config.enable_black_fades,
                    "enable_white_fades": v.config.enable_white_fades,
                    "enable_visual_cuts": v.config.enable_visual_cuts,
                    "enable_subdivide": v.config.enable_subdivide,
                    "card_dur": v.config.card_dur,
                    "title_template": v.config.title_template,
                },
            }
            for k, v in PRESETS.items()
        },
        ensure_ascii=False,
    )
    return (
        template.replace("__DEFAULT_CFG__", cfg_json)
        .replace("__PRESETS__", presets_json)
        .replace("__INIT_DIR__", json.dumps(default_dir, ensure_ascii=False))
        .replace("__INIT_VID__", json.dumps(initial_video, ensure_ascii=False))
    )
