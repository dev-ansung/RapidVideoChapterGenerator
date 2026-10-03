# RapidVideoChapterGenerator

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://python.org)
[![Zero Re-encode](https://img.shields.io/badge/Video%20Quality-100%25%20Lossless-orange.svg)](#technical-overview)
[![Platform Compatibility](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#installation)

**RapidVideoChapterGenerator** automatically detects scene boundaries and injects native chapter markers into video files at ~3,400× real-time speed. Processing is 100% lossless (`-c copy`), requires zero re-encoding, and works out of the box across QuickTime, IINA, VLC, mpv, Plex, and YouTube.

[![RapidVideoChapterGenerator Demo](docs/demo.gif)](docs/demo.mp4)

---

## Key Capabilities

* **Multi-Core Keyframe Acceleration:** Partitions video timelines across parallel workers using I-frame-only decoding (`-skip_frame nokey`) and $240\times 135$ downscaled luminance/scene analysis to scan multi-hour videos in seconds.
* **5-Stage Hybrid Boundary Solver:** Combines fade-to-black detection (`blackdetect`) with perceptual visual cut scoring (`select='gt(scene,...)'`), priority anchor placement, smart long-segment subdivision, and micro-tail merging.
* **Lossless Atomic Injection:** Operates exclusively at the container level (`-c copy -movflags +faststart`). Video bitstreams, audio tracks, HDR/Dolby Vision metadata, and embedded subtitles remain untouched, with safe atomic in-place replacement.
* **Native Player Support:** Writes standard container chapter atoms (`chpl` / `FFMETADATA1`) recognized natively by QuickTime Player, IINA, VLC, mpv, Apple TV, Plex, and Jellyfin.
* **Multi-Format Export & 3×3 Web Browser:** Supports direct container muxing, plain-text export (`youtube`, `json`, `csv`, `ffmetadata`), and an optional zero-server **3×3 interactive HTML5 scene browser** (`--browse`) with live cell hover previews.

---

## Performance Benchmark

Test environment: **11 hr 35 min (7.2 GB)** 1080p AVC video on Apple Silicon (8 parallel workers).

| Method | Execution Time (11.5h Video) | Execution Time (1h Video) | Output Quality | Manual Effort |
| :--- | :---: | :---: | :---: | :---: |
| Manual Timestamping | 45–90 minutes | 15–30 minutes | 100% | High |
| Full-Frame Scene Detectors (`PySceneDetect`) | 18–35 minutes | 2–4 minutes | 100% | Low |
| Re-encoding / Transcoding Tools | 40–90 minutes | 5–12 minutes | Degraded | Low |
| **RapidVideoChapterGenerator** | **12.0 seconds** | **~1.2 seconds** | **100% (Lossless)** | **None** |

---

## Installation

### Prerequisites

Requires `ffmpeg` (`ffmpeg` and `ffprobe`) installed and available in your system `PATH`:

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# Windows (winget)
winget install Gyan.FFmpeg
```

### Run Instantly with `uvx` (Zero Install)

```bash
uvx --from git+https://github.com/dev-ansung/RapidVideoChapterGenerator.git rapid-chapters input.mp4
```

### Install via `uv` or `pip`

```bash
# Install globally as a CLI tool via uv
uv tool install git+https://github.com/dev-ansung/RapidVideoChapterGenerator.git

# Or install from source in editable mode
git clone https://github.com/dev-ansung/RapidVideoChapterGenerator.git
cd RapidVideoChapterGenerator
uv pip install -e .
```

---

## Quick Start

### 1. Detect Scenes and Embed Chapters In-Place (Default)

Atomically inject native chapter markers directly into the input video without creating duplicate files:

```bash
rapid-chapters input.mp4
```

Or write to a separate output container:

```bash
rapid-chapters input.mp4 -o output.mp4
```

### 2. Web Lifecycle Studio (No-Argument Frontend)

Run without arguments (or pass `--ui`) to launch the **Web Lifecycle Studio** in your browser—handling directory/file selection, live 5-phase SSE progress, 3×3 contact-sheet browsing, interactive chapter editing (rename, split at playhead, delete/merge), and lossless `-c copy` saving:

```bash
rapid-chapters
```

### 3. Export YouTube Description Timestamps

Generate formatted chapter timestamps to `stdout` without modifying the video file:

```bash
rapid-chapters input.mp4 --format youtube
```

Output:

```text
00:00:00 - Scene 01
00:05:42 - Scene 02
00:12:18 - Scene 03
00:19:04 - Scene 04
```

### 4. Launch the 3×3 Interactive Scene Browser

Embed chapters and open a zero-server HTML5 3×3 contact-sheet gallery with live cell hover previews and seekbar thumbnail scrubbing:

```bash
rapid-chapters input.mp4 --browse
```

---

## Common Use Cases

### Long-Form VODs, Archives, and Raw Footage
Keep chapters within a comfortable 3-to-10 minute window while snapping splits to natural camera cuts:

```bash
rapid-chapters archive.mp4 --min-scene-len 180 --max-scene-len 600 --target-scene-len 360
```

### Podcasts and Interviews
Avoid triggering chapter splits on rapid camera angle switches by increasing the minimum scene duration and scene score threshold:

```bash
rapid-chapters interview.mp4 --min-scene-len 120 --threshold 0.45
```

### Slide Presentations and Lectures
Use the presentation preset to capture crisp slide transitions:

```bash
rapid-chapters lecture.mp4 --preset presentation -o lecture_chaptered.mp4
```

---

## Player and Platform Compatibility

| Target | Embedded Container Chapters | Timestamp / Metadata Export |
| :--- | :---: | :---: |
| **IINA / mpv** | Supported (Timeline ticks & chapter menu) | Not Applicable |
| **QuickTime Player** | Supported | Not Applicable |
| **VLC Media Player** | Supported (`Playback > Chapters`) | Not Applicable |
| **Plex / Jellyfin** | Supported | Not Applicable |
| **YouTube** | Not Applicable | Supported (`--format youtube`) |
| **Podcasting 2.0 / Pipelines** | Not Applicable | Supported (`--format json` / `csv`) |

---

## Command-Line Interface

```text
Usage: rapid-chapters [OPTIONS] [INPUT_VIDEO]

Arguments:
  [INPUT_VIDEO]                   Path to target video file (omit for interactive prompt loop)

Detection Controls:
  -t, --threshold FLOAT           Visual cut sensitivity (0.0 to 1.0) [default: 0.38]
  -m, --min-scene-len SECONDS     Minimum duration between chapters [default: 180]
  -M, --max-scene-len SECONDS     Maximum duration before smart subdivision [default: 600]
  --target-scene-len SECONDS      Target duration when subdividing long gaps [default: 360]
  --preset [default|podcast|presentation|action]
                                  Predefined detection sensitivity profile
  -w, --workers INT               Parallel FFmpeg keyframe worker count [default: 8]

Output Options:
  -o, --output PATH               Destination file path (defaults to atomic in-place update)
  -f, --format [mp4|youtube|ffmetadata|json|csv]
                                  Output mode [default: mp4]
  --title-template TEXT           Chapter naming template [default: "Scene {n:02d}"]
  --browse                        Launch interactive 3x3 HTML5 scene browser after processing
  --refresh                       Force re-scan even if embedded chapters or cached browser exist
```

---

## Technical Overview

1. **Embedded Chapter Fast-Path (`Phase 1`):** Probes container metadata first via `ffprobe`; if chapters are already present and `--refresh` is not set, reuses them in $<50\text{ ms}$.
2. **Parallel Keyframe Visual Scan (`Phase 2`):** Splits the timeline into $N$ chunks across worker processes, decodes only I-frames (`-skip_frame nokey`), downscales to $240\times 135$ (`fast_bilinear`), and runs `blackdetect` + `select='gt(scene,th)'` in a single filtergraph pass.
3. **Priority Anchor Placement (`Phase 3`):** Places primary boundary anchors at black-frame transitions first, then greedily inserts the highest-scoring visual cuts that satisfy `--min-scene-len`.
4. **Smart Long-Segment Subdivision (`Phase 4`):** Subdivides any remaining segments longer than `--max-scene-len` toward `--target-scene-len`, snapping subdivision cuts to nearby visual transitions within a $\pm 45\text{s}$ window.
5. **Tail Merge & Lossless Remux (`Phase 5`):** Merges trailing micro-segments ($<20\text{s}$), generates an `FFMETADATA1` chapter manifest, and runs `ffmpeg -map 0 -map_metadata 1 -map_chapters 1 -c copy` into a temporary sibling file before atomically replacing the target video.

---

## Contributing

Pull requests and issues are welcome:

1. Fork the repository.
2. Create an isolated feature branch (`git checkout -b feature/improvement`).
3. Run the verification suite (`uv run ruff check . && uv run mypy --strict src tests && uv run pytest`).
4. Commit your changes using conventional commits (`git commit -m "feat(solver): add presentation preset"`).
5. Push to your branch and open a Pull Request.

---

## License

This project is licensed under the [MIT License](LICENSE).
