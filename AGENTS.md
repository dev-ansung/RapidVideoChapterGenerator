# AGENTS.md — RapidVideoChapterGenerator (`rvcg`)

## 1. System Overview & Core Value Proposition
`RapidVideoChapterGenerator` (`rvcg` / `rapid-chapters`) detects scene boundaries and generates chapter markers + thumbnail galleries for long-form videos (4K movies, lectures, VODs) in under 5 seconds.

Instead of decoding every frame at full resolution (`O(N_frames * W * H)`), `rvcg` demuxes only compressed **I-frames (keyframes)** (`-skip_frame nokey`), downscales them in-pipe to `16x8` grayscale (`128 bytes/frame`), computes 64-bit horizontal gradient perceptual hashes (**dHash**) + luminance histograms, and solves for the globally optimal chapter partition via **Dynamic Programming**.

---

## 2. Architecture & Module Map

```text
src/rvcg/
├── models.py        # Strictly typed, immutable dataclasses (KeyframeSample, CandidateCut, ChapterMark, ScanConfig, ScanResult)
├── scanner.py       # FFprobe duration cascade + single-pass FFmpeg keyframe pipe (16x8 gray rawvideo + showinfo pts_time)
├── solver.py        # 64-bit dHash + histogram intersection + MAD z-score + DP partition solver (solve_chapter_partition)
├── muxer.py         # FFMETADATA1 serializer/parser + atomic temp-file remuxing (-c copy)
├── thumbnails.py    # Fast input-seeking (-ss before -i) 320px JPEG chapter thumbnail extractor
├── html_export.py   # Standalone interactive HTML5 player + chapter card gallery generator
├── server.py        # Multi-threaded local Web UI server (HTTP 206 Range streaming, SSE progress, SHA-256 cache, SRT->WebVTT)
├── cli.py           # CLI entry point (Web UI launcher when called with no args, or batch CLI mode)
└── static/
    ├── webui.html   # Full-featured studio Web UI (Tippy.js file list, interact.js floating player, Video.js, SSE modal)
    └── browser.html # Standalone HTML export template rendered by html_export.py
```

---

## 3. Proprietary Engineering Knowledge & Gotchas

### 3.1 Single-Pass Keyframe Pipe & Deadlock Prevention (`scanner.py`)
- **Why both `stdout` and `stderr` are used simultaneously**:
  `ffmpeg -skip_frame nokey -i <video> -vf showinfo,scale=16:8:flags=fast_bilinear,format=gray -f rawvideo pipe:1` emits raw 128-byte grayscale frames to `stdout` and `pts_time:<float>` diagnostics from the `showinfo` filter to `stderr`.
- **Deadlock hazard**:
  Reading `stdout` to EOF before reading `stderr` (or vice versa) **will deadlock** on 2+ hour movies when the OS pipe buffer (64 KB) fills up. Always drain `stderr` concurrently on a background daemon `threading.Thread` while reading exact 128-byte chunks (`FRAME_BYTES = 16 * 8`) from `stdout`.
- **Non-UTF8 Container Metadata**:
  Legacy MP4/AVI/MKV containers frequently embed Latin-1 or Windows-1252 bytes in copyright/comment tags (`©cmt`, `©nam`), which `ffmpeg` echoes to `stderr`. Always invoke `subprocess.run` and `subprocess.Popen` with `encoding="utf-8", errors="replace"` when reading text streams.
- **3-Tier Duration Probe Cascade (`probe_duration`)**:
  Containers like `.flv`, `.ts`, or truncated `.mkv` files often report `"N/A"` or `0` for `format.duration`. `probe_duration()` must cascade through:
  1. `format.duration`
  2. Maximum positive numeric `streams[].duration`
  3. `ffprobe -v error -select_streams v:0 -skip_frame nokey -show_entries packet=pts_time -of csv=p=0` (last keyframe packet timestamp).

### 3.2 Perceptual Novelty & Dynamic Programming Partition (`solver.py`)
- **Signal fusion**:
  Raw frame-to-frame difference is vulnerable to camera flashes and compression noise. `solver.py` combines:
  - **64-bit dHash Hamming distance** (structural layout change, weight `0.65`)
  - **16-bin luminance histogram L1 distance** (lighting/color palette shift, weight `0.35`)
  - **Local window contrast**: Compares average pre-window vs. post-window hash distance (`window_size=3`) to suppress single-keyframe camera flashes.
- **Robust Normalization**:
  Novelty scores are normalized using **Median Absolute Deviation (MAD)** (`robust_z = (x - median) / (1.4826 * mad)`), making threshold parameter `--threshold` invariant across dark movies, bright anime, and static lecture recordings.
- **DP Objective (`solve_chapter_partition`)**:
  Given candidate cuts filtered by local temporal debounce, the DP solver maximizes:
  $$\sum_{k} \left(\text{novelty}(i_k) - \lambda \cdot \left(\frac{\Delta t_k - T_{\text{target}}}{T_{\text{target}}}\right)^2\right)$$
  subject to hard minimum chapter duration (`min_chapter_sec`) and maximum chapter count (`max_chapters`).

### 3.3 Lossless Muxing & Atomic Replacement (`muxer.py`)
- **Container-specific flags**:
  `-movflags +faststart` is strictly valid for MP4-family containers (`.mp4`, `.m4v`, `.mov`). Never pass `-movflags +faststart` when remuxing `.mkv`, `.webm`, `.avi`, or `.flv`.
- **Atomic staging**:
  Always write the remuxed output to a hidden sibling file in the **same directory** (`.<stem>.rvcg_tmp<suffix>`) so `os.replace(temp_path, video_path)` is an atomic POSIX rename on the same filesystem mount. Clean up `temp_path` in the `except` block if `ffmpeg` exits non-zero.

### 3.4 Web UI & Local Media Server (`server.py` & `static/webui.html`)
- **Non-Destructive Scan vs. Explicit Chapter Embedding**:
  - `POST /api/scan` runs keyframe extraction, DP solving, thumbnail generation, and writes to `~/.cache/rvcg/chapters/<sha256>.json`, but **does not modify the video file**.
  - `POST /api/save_chapters` calls `embed_chapters_atomic()` only when the user explicitly clicks **`Embed Chapters`** (`#save-chapters-btn`). After atomic replacement changes the file's `mtime_ns` and `size`, `/api/save_chapters` immediately writes a fresh cache entry keyed by the new `(resolved_path, size, mtime_ns)` SHA-256 signature so the user never has to re-scan.
- **HTTP 206 Partial Content Streaming**:
  Browsers and `Video.js` require `Accept-Ranges: bytes` and `206 Partial Content` responses (`Content-Range: bytes start-end/total`) to scrub smoothly through multi-gigabyte video files. `BrokenPipeError` and `ConnectionResetError` during chunk streaming are normal browser seek behavior and must be caught silently.
- **Subtitle Auto-Discovery & On-the-Fly WebVTT (`_find_First_subtitle`, `_srt_to_vtt`)**:
  HTML5 `<track>` elements only accept `WEBVTT`. `server.py` automatically discovers matching `.srt` / `.vtt` files (exact stem match first, then language-tagged `.en.srt` / `.eng.srt`, then single-subtitle fallback in the folder) and converts `.srt` timestamps (`00:01:23,456` -> `00:01:23.456`) on the fly at `/api/subtitles`.
- **Floating Draggable & 8-Edge Resizable Player (`interact.js` + `Video.js`)**:
  - `#player-shell` is a single floating window (`position: fixed`) controlled via CSS custom properties (`--win-x`, `--win-y`, `--win-w`).
  - Configure `interact('#player-shell').draggable({ ignoreFrom: 'button, .vjs-control-bar, input' })` so timeline scrubbing and button clicks do not drag the window.
  - Configure `interact('#player-shell').resizable({ edges: { left: true, right: true, bottom: true, top: true }, margin: 12 })` for 8-direction edge/corner resizing.
- **Full-Filename Hover Tooltips (`Tippy.js`)**:
  Long scene/release filenames in `#file-grid` use a single-column list layout with `Tippy.js` (`@popperjs/core` + `tippy.js`, `placement: 'top-start'`) so truncated filenames display in full on hover.

---

## 4. Development, Testing & Release Playbook

### Verification Gate (Pre-Commit & CI)
Every commit is gated by `.git/hooks/pre-commit` and `.github/workflows/ci.yml`:
```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src tests
uv run pytest -q
```

### CI Environment Note
- GitHub Actions `macos-latest` images do **not** include `ffmpeg` by default and `brew install ffmpeg` adds several minutes of overhead. Keep `.github/workflows/ci.yml` on `ubuntu-latest` across Python `["3.11", "3.12", "3.13"]` with `which ffmpeg || (sudo apt-get update && sudo apt-get install -y ffmpeg)`.

### Packaging & Release
- Static HTML files (`src/rvcg/static/webui.html`, `src/rvcg/static/browser.html`) must remain inside `src/rvcg/static/` so `hatchling` (`packages = ["src/rvcg"]`) bundles them into wheels and sdists for zero-install `uvx` execution:
  ```bash
  uv build
  gh release upload v0.1.0 dist/* --clobber
  ```
