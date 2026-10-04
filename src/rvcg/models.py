from dataclasses import dataclass, field
from typing import Protocol


def fmt_hms(sec: float) -> str:
    s = max(0, int(round(sec)))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def fmt_ms(sec: float) -> str:
    s = max(0, int(round(sec)))
    if s >= 3600:
        return fmt_hms(sec)
    return f"{s // 60:02d}:{s % 60:02d}"


class PhaseProgressCallback(Protocol):
    def __call__(self, phase: int, completed: float, total: float, info: str) -> None: ...


class SpriteProgressCallback(Protocol):
    def __call__(self, completed: float) -> None: ...


@dataclass(frozen=True)
class BoundaryConfig:
    min_seg: float = 180.0
    max_seg: float = 600.0
    target_seg: float = 360.0
    workers: int = 8
    scene_threshold: float = 0.38
    black_min_dur: float = 0.4
    black_pic_th: float = 0.95
    white_pic_th: float = 0.95
    black_pix_th: float = 0.12
    white_pix_th: float = 0.10
    enable_black_fades: bool = True
    enable_white_fades: bool = True
    enable_visual_cuts: bool = False
    enable_subdivide: bool = False
    card_dur: float = 8.4
    title_template: str = "Scene {n:02d}"

    @classmethod
    def from_preset(cls, preset: str) -> "BoundaryConfig":
        p = preset.strip().lower()
        if p in ("movie", "black-fades", "fades"):
            p = "default"
        elif p == "all-stages":
            p = "balanced"
        if p in PRESETS:
            return PRESETS[p].config
        return cls()


@dataclass(frozen=True)
class PresetMetadata:
    id: str
    name: str
    description: str
    config: BoundaryConfig


PRESETS: dict[str, PresetMetadata] = {
    "default": PresetMetadata(
        id="default",
        name="movie (Fades only - High Precision)",
        description="High-precision fade detection only. Ideal for films, cinema, and narrative storytelling where scene transitions are intentional fades.",
        config=BoundaryConfig(
            min_seg=180.0,
            max_seg=720.0,
            target_seg=360.0,
            workers=8,
            scene_threshold=0.38,
            black_min_dur=0.40,
            black_pic_th=0.95,
            black_pix_th=0.12,
            white_pic_th=0.95,
            white_pix_th=0.10,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=False,
            enable_subdivide=False,
            card_dur=8.4,
            title_template="Scene {n:02d}",
        ),
    ),
    "balanced": PresetMetadata(
        id="balanced",
        name="balanced (Fades + Visual + Subdivide)",
        description="Full 3-stage pipeline combining fades, visual cuts, and subdivision. Best all-rounder for YouTube videos, documentaries, and mixed media.",
        config=BoundaryConfig(
            min_seg=120.0,
            max_seg=600.0,
            target_seg=300.0,
            workers=8,
            scene_threshold=0.38,
            black_min_dur=0.40,
            black_pic_th=0.95,
            black_pix_th=0.12,
            white_pic_th=0.95,
            white_pix_th=0.10,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=True,
            enable_subdivide=True,
            card_dur=8.4,
            title_template="Scene {n:02d}",
        ),
    ),
    "podcast": PresetMetadata(
        id="podcast",
        name="podcast (Interviews & Long Talks)",
        description="Long conversational chapters. Uses a higher visual threshold to ignore 2-person alternating camera switches while subdividing long monolithic discussions.",
        config=BoundaryConfig(
            min_seg=180.0,
            max_seg=900.0,
            target_seg=480.0,
            workers=8,
            scene_threshold=0.46,
            black_min_dur=0.40,
            black_pic_th=0.95,
            black_pix_th=0.12,
            white_pic_th=0.95,
            white_pix_th=0.10,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=True,
            enable_subdivide=True,
            card_dur=10.0,
            title_template="Chapter {n:02d}",
        ),
    ),
    "presentation": PresetMetadata(
        id="presentation",
        name="presentation (Slides & Keynotes)",
        description="Slide and topic transitions. Sensitive visual detection catches slide changes that don't shift the entire screen background.",
        config=BoundaryConfig(
            min_seg=60.0,
            max_seg=600.0,
            target_seg=300.0,
            workers=8,
            scene_threshold=0.28,
            black_min_dur=0.35,
            black_pic_th=0.95,
            black_pix_th=0.10,
            white_pic_th=0.95,
            white_pix_th=0.10,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=True,
            enable_subdivide=True,
            card_dur=5.0,
            title_template="Slide {n:02d}",
        ),
    ),
    "anime": PresetMetadata(
        id="anime",
        name="anime (TV Episodes & Series)",
        description="Optimized for 20-45m anime and TV episodes with distinct OP/ED, eyecatches, mid-episode commercial fades, and post-credits previews.",
        config=BoundaryConfig(
            min_seg=60.0,
            max_seg=480.0,
            target_seg=240.0,
            workers=8,
            scene_threshold=0.36,
            black_min_dur=0.30,
            black_pic_th=0.92,
            black_pix_th=0.15,
            white_pic_th=0.92,
            white_pix_th=0.12,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=True,
            enable_subdivide=True,
            card_dur=6.0,
            title_template="Part {n:02d}",
        ),
    ),
    "action": PresetMetadata(
        id="action",
        name="action (Sports, Gaming & Action)",
        description="High-motion gameplay, sports, and fast-cut action. Raised threshold prevents false cuts during combat while subdividing into compact chapters.",
        config=BoundaryConfig(
            min_seg=90.0,
            max_seg=420.0,
            target_seg=210.0,
            workers=8,
            scene_threshold=0.42,
            black_min_dur=0.40,
            black_pic_th=0.90,
            black_pix_th=0.15,
            white_pic_th=0.90,
            white_pix_th=0.15,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=True,
            enable_subdivide=True,
            card_dur=6.0,
            title_template="Highlight {n:02d}",
        ),
    ),
    "fine": PresetMetadata(
        id="fine",
        name="fine (Micro / Granular Chapters)",
        description="Granular chapter boundaries for music videos, highlight reels, micro-tutorials, and rapid navigation.",
        config=BoundaryConfig(
            min_seg=30.0,
            max_seg=180.0,
            target_seg=90.0,
            workers=8,
            scene_threshold=0.32,
            black_min_dur=0.25,
            black_pic_th=0.90,
            black_pix_th=0.15,
            white_pic_th=0.90,
            white_pix_th=0.15,
            enable_black_fades=True,
            enable_white_fades=True,
            enable_visual_cuts=True,
            enable_subdivide=True,
            card_dur=4.0,
            title_template="Segment {n:02d}",
        ),
    ),
}


@dataclass(frozen=True)
class FadePoint:
    timestamp: float
    duration: float = 0.0

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FadePoint):
            return self.timestamp < other.timestamp
        if isinstance(other, (int, float)):
            return self.timestamp < float(other)
        return NotImplemented


@dataclass(frozen=True)
class VisualCut:
    timestamp: float
    score: float


@dataclass(frozen=True)
class RawScanResult:
    black_points: list[FadePoint | float] = field(default_factory=list)
    white_points: list[FadePoint | float] = field(default_factory=list)
    visual_cuts: list[VisualCut] = field(default_factory=list)

    def to_candidates_list(self) -> list[dict[str, str | float]]:
        items: list[dict[str, str | float]] = []
        for bp in self.black_points:
            ts = bp.timestamp if isinstance(bp, FadePoint) else float(bp)
            dur = bp.duration if isinstance(bp, FadePoint) else 0.0
            dur_str = f" ({dur:.2f}s fade)" if dur > 0 else ""
            items.append(
                {
                    "timestamp": round(ts, 2),
                    "kind": "black",
                    "score": 2.0,
                    "detail": f"Black fade @ {fmt_hms(ts)}{dur_str}",
                }
            )
        for wp in self.white_points:
            ts = wp.timestamp if isinstance(wp, FadePoint) else float(wp)
            dur = wp.duration if isinstance(wp, FadePoint) else 0.0
            dur_str = f" ({dur:.2f}s fade)" if dur > 0 else ""
            items.append(
                {
                    "timestamp": round(ts, 2),
                    "kind": "white",
                    "score": 2.0,
                    "detail": f"White fade @ {fmt_hms(ts)}{dur_str}",
                }
            )
        for vc in self.visual_cuts:
            items.append(
                {
                    "timestamp": round(vc.timestamp, 2),
                    "kind": "visual",
                    "score": round(vc.score, 3),
                    "detail": f"Visual cut @ {fmt_hms(vc.timestamp)} (score={vc.score:.3f})",
                }
            )
        items.sort(key=lambda x: float(x["timestamp"]))
        return items


@dataclass(frozen=True)
class BoundaryStats:
    raw_black: int = 0
    used_black: int = 0
    raw_white: int = 0
    used_white: int = 0
    raw_visual: int = 0
    used_visual: int = 0
    sub_cuts: int = 0
    snapped_cuts: int = 0
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, int]:
        return {
            "raw_black": self.raw_black,
            "used_black": self.used_black,
            "raw_white": self.raw_white,
            "used_white": self.used_white,
            "raw_visual": self.raw_visual,
            "used_visual": self.used_visual,
            "sub_cuts": self.sub_cuts,
            "snapped_cuts": self.snapped_cuts,
        }


@dataclass(frozen=True)
class SceneSegment:
    index: int
    start_time: float
    end_time: float
    title: str
    cell_times: list[float]
    card_dur: float = 8.4
    cut_kind: str = "start"
    cut_detail: str = "Video start (00:00:00)"

    @property
    def id_str(self) -> str:
        return f"{self.index:02d}"

    @property
    def duration(self) -> float:
        return round(max(1.0, self.end_time - self.start_time), 2)

    @property
    def duration_str(self) -> str:
        return fmt_ms(self.duration)

    @property
    def source_range(self) -> str:
        return f"{fmt_hms(self.start_time)} – {fmt_hms(self.end_time)}"

    @property
    def cell_labels(self) -> list[str]:
        return [fmt_hms(t) for t in self.cell_times]

    def to_dict(self) -> dict[str, str | int | float | list[float] | list[str]]:
        return {
            "id": self.id_str,
            "id_str": self.id_str,
            "scene_number": self.index,
            "index": self.index,
            "title": self.title,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
            "source_range": self.source_range,
            "duration": self.duration,
            "duration_str": self.duration_str,
            "card_dur": self.card_dur,
            "cell_times": self.cell_times,
            "cell_labels": self.cell_labels,
            "cut_kind": self.cut_kind,
            "cut_detail": self.cut_detail,
        }


@dataclass(frozen=True)
class SpriteMeta:
    url: str
    interval: int
    cols: int
    rows: int
    total_frames: int
    width: int = 240
    height: int = 135

    def to_dict(self) -> dict[str, str | int]:
        return {
            "url": self.url,
            "interval": self.interval,
            "cols": self.cols,
            "rows": self.rows,
            "total_frames": self.total_frames,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class SubtitleTrack:
    label: str
    srclang: str
    vtt: str
    default: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "label": self.label,
            "srclang": self.srclang,
            "vtt": self.vtt,
            "default": self.default,
        }
