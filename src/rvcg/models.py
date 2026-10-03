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
    enable_black_fades: bool = True
    enable_visual_cuts: bool = True
    enable_subdivide: bool = True
    card_dur: float = 8.4
    title_template: str = "Scene {n:02d}"

    @classmethod
    def from_preset(cls, preset: str) -> "BoundaryConfig":
        if preset == "black-fades":
            return cls(enable_black_fades=True, enable_visual_cuts=False, enable_subdivide=False)
        if preset == "podcast":
            return cls(min_seg=120.0, max_seg=900.0, target_seg=450.0, scene_threshold=0.45)
        if preset == "presentation":
            return cls(min_seg=60.0, max_seg=600.0, target_seg=300.0, scene_threshold=0.30)
        if preset == "action":
            return cls(min_seg=90.0, max_seg=420.0, target_seg=240.0, scene_threshold=0.35)
        return cls()


@dataclass(frozen=True)
class VisualCut:
    timestamp: float
    score: float


@dataclass(frozen=True)
class RawScanResult:
    black_points: list[float] = field(default_factory=list)
    visual_cuts: list[VisualCut] = field(default_factory=list)


@dataclass(frozen=True)
class BoundaryStats:
    raw_black: int = 0
    used_black: int = 0
    raw_visual: int = 0
    used_visual: int = 0
    sub_cuts: int = 0
    snapped_cuts: int = 0
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, int]:
        return {
            "raw_black": self.raw_black,
            "used_black": self.used_black,
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
            "scene_number": self.index,
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
