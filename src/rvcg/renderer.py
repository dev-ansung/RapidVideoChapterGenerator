import json
from pathlib import Path

from rvcg.models import SceneSegment, SpriteMeta, SubtitleTrack


def write_index_html(
    out_dir: Path,
    video_title: str,
    video_src_rel: str,
    segments: list[SceneSegment],
    sprite_meta: SpriteMeta,
    sub_tracks: list[SubtitleTrack],
) -> Path:
    items = [s.to_dict() for s in segments]
    sprite = sprite_meta.to_dict()
    subs = [t.to_dict() for t in sub_tracks]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{video_title}</title>
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  :root {{
    --bg: #0b0c10;
    --panel: #12141c;
    --border: #232736;
    --accent: #3b82f6;
    --text: #f3f4f6;
    --muted: #9ca3af;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
  }}
  .layout {{
    max-width: 1720px;
    margin: 0 auto;
    padding: 20px 24px 48px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }}
  .toolbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
  }}
  .brand {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }}
  .search-input {{
    flex: 1;
    min-width: 260px;
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 9px 12px;
    font-size: 13px;
    outline: none;
  }}
  .search-input:focus {{
    border-color: var(--accent);
  }}
  button {{
    background: #1b1f2e;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 7px 11px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
    transition: background 0.12s ease, border-color 0.12s ease;
  }}
  button:hover {{
    background: #252b3f;
    border-color: var(--accent);
  }}
  .toolbar-right {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .view-btn.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }}
  .count-label {{
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    margin-right: 4px;
  }}
  .gallery {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 0;
  }}
  .card {{
    background: #000;
    border: 1.5px solid #2e3448;
    border-radius: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    filter: brightness(0.62);
    transition: border-color 0.15s ease, filter 0.18s ease;
  }}
  .card:hover,
  .card.active {{
    border-color: var(--accent);
    filter: brightness(1);
    z-index: 2;
  }}
  .card-body {{
    display: none;
  }}
  .gallery.list-view {{
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  .gallery.list-view .card {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    flex-direction: row;
    align-items: stretch;
  }}
  .gallery.list-view .card-body {{
    display: flex;
    width: 220px;
    flex-shrink: 0;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    border-right: 1px solid var(--border);
    padding: 12px 14px;
    order: -1;
    cursor: pointer;
  }}
  .gallery.list-view .contact-grid {{
    flex: 1;
    aspect-ratio: auto;
    height: 112px;
    grid-template-columns: repeat(8, 1fr);
    grid-template-rows: 1fr;
  }}
  .gallery.list-view .center-cell {{
    display: none;
  }}
  .contact-grid {{
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(3, 1fr);
    gap: 2px;
    padding: 2px;
  }}
  .grid-cell {{
    position: relative;
    overflow: hidden;
    background-color: #050608;
    background-repeat: no-repeat;
    cursor: pointer;
    border: 1px solid transparent;
    transition: border-color 0.1s ease;
  }}
  .grid-cell:hover {{
    border-color: var(--accent);
  }}
  .grid-cell video {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    z-index: 1;
    pointer-events: none;
  }}
  .cell-time {{
    position: absolute;
    left: 0;
    bottom: 0;
    z-index: 2;
    padding: 1px 4px;
    font-family: Menlo, Monaco, monospace;
    font-size: 10px;
    font-weight: 600;
    color: #fff;
    background: rgba(0, 0, 0, 0.72);
    font-variant-numeric: tabular-nums;
    pointer-events: none;
    line-height: 1.25;
  }}
  .center-cell {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 4px;
    background: #000;
    cursor: pointer;
    gap: 2px;
  }}
  .center-cell:hover {{
    background: #0c101d;
    border-color: var(--accent);
  }}
  .center-badge {{
    font-family: Menlo, monospace;
    font-size: 10px;
    font-weight: 700;
    color: var(--accent);
  }}
  .center-title {{
    font-size: 11px;
    font-weight: 700;
    color: #f3f4f6;
    line-height: 1.2;
  }}
  .center-range {{
    font-family: Menlo, monospace;
    font-size: 9.5px;
    color: #9ca3af;
  }}
  .center-dur {{
    font-family: Menlo, monospace;
    font-size: 9px;
    color: #6b7280;
  }}
  .card-id {{
    font-size: 12px;
    font-weight: 700;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }}
  .card-meta {{
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  #video-popover {{
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    color: var(--text);
    padding: 0;
    width: min(92vw, 1280px);
    max-height: 92vh;
    margin: auto;
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.85);
    overflow: hidden;
  }}
  #video-popover::backdrop {{
    background: rgba(0, 0, 0, 0.82);
    backdrop-filter: blur(4px);
  }}
  .popover-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 14px;
    background: #0e1017;
    border-bottom: 1px solid var(--border);
  }}
  .popover-meta {{
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }}
  .badge {{
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 12px;
    background: var(--accent);
    color: #fff;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }}
  .popover-title {{
    font-size: 13.5px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .popover-range {{
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }}
  .close-btn {{
    padding: 4px 10px;
    font-size: 13px;
    line-height: 1;
  }}
  .player-stage {{
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
  }}
  .video-js {{
    width: 100% !important;
    height: 100% !important;
  }}
  .vjs-sprite-tooltip {{
    position: absolute;
    bottom: 18px;
    transform: translateX(-50%);
    width: 192px;
    height: 108px;
    border-radius: 5px;
    border: 1.5px solid rgba(255, 255, 255, 0.85);
    background-color: #000;
    background-repeat: no-repeat;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.75);
    pointer-events: none;
    display: none;
    z-index: 20;
  }}
  .vjs-progress-control:hover .vjs-sprite-tooltip {{
    display: block;
  }}
  .vjs-chapter-marker {{
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: rgba(255, 255, 255, 0.55);
    pointer-events: none;
    z-index: 5;
  }}
</style>
</head>
<body>
<div class="layout">
  <section class="toolbar">
    <div class="brand">{video_title}</div>
    <input id="search-input" class="search-input" type="search" placeholder="Search scene ID or timestamp..." />
    <div class="toolbar-right">
      <span id="count-label" class="count-label"></span>
      <button type="button" class="view-btn active" data-view="grid">Grid</button>
      <button type="button" class="view-btn" data-view="list">List</button>
    </div>
  </section>

  <section id="gallery" class="gallery"></section>
</div>

<dialog id="video-popover">
  <div class="popover-header">
    <div class="popover-meta">
      <span id="now-badge" class="badge"></span>
      <span id="now-title" class="popover-title"></span>
      <span id="now-range" class="popover-range"></span>
    </div>
    <button id="close-popover" class="close-btn" type="button">✕</button>
  </div>
  <div class="player-stage">
    <video id="vjs-player" class="video-js vjs-big-play-centered" controls playsinline preload="metadata"></video>
  </div>
</dialog>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
const VIDEO_SRC = {json.dumps(video_src_rel)};
const SPRITE = {json.dumps(sprite)};
const CUTS = {json.dumps(items, ensure_ascii=False)};
const SUBTITLES = {json.dumps(subs, ensure_ascii=False)};

const popoverEl = document.getElementById("video-popover");
const closeBtn = document.getElementById("close-popover");
const nowBadge = document.getElementById("now-badge");
const nowRange = document.getElementById("now-range");
const nowTitle = document.getElementById("now-title");
const gallery = document.getElementById("gallery");
const searchInput = document.getElementById("search-input");
const countLabel = document.getElementById("count-label");

const player = videojs("vjs-player", {{
  controls: true,
  autoplay: false,
  preload: "metadata",
  fluid: false,
  playbackRates: [0.5, 1, 1.25, 1.5, 2],
  controlBar: {{
    SkipButtons: {{ forward: 10, backward: 10 }}
  }}
}});

let currentIndex = -1;
let searchQuery = "";
let sourceLoaded = false;

const CELL_TO_SLOT = [0, 1, 2, 3, -1, 4, 5, 6, 7];

function fmtHmsMs(sec) {{
  const s = Math.max(0, sec);
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 1000);
  return (
    String(hh).padStart(2, "0") + ":" +
    String(mm).padStart(2, "0") + ":" +
    String(ss).padStart(2, "0") + "." +
    String(ms).padStart(3, "0")
  );
}}

function setCellSpriteFrame(el, timeSec) {{
  const frameIdx = Math.max(0, Math.min(SPRITE.total_frames - 1, Math.floor(timeSec / SPRITE.interval)));
  const col = frameIdx % SPRITE.cols;
  const row = Math.floor(frameIdx / SPRITE.cols);
  const xPct = SPRITE.cols > 1 ? (col / (SPRITE.cols - 1)) * 100 : 0;
  const yPct = SPRITE.rows > 1 ? (row / (SPRITE.rows - 1)) * 100 : 0;
  el.style.backgroundImage = `url("${{SPRITE.url}}")`;
  el.style.backgroundSize = `${{SPRITE.cols * 100}}% ${{SPRITE.rows * 100}}%`;
  el.style.backgroundPosition = `${{xPct.toFixed(3)}}% ${{yPct.toFixed(3)}}%`;
}}

player.ready(() => {{
  const progressControl = player.controlBar.progressControl;
  const seekBar = progressControl.seekBar;

  const spriteTip = document.createElement("div");
  spriteTip.className = "vjs-sprite-tooltip";
  seekBar.el().appendChild(spriteTip);

  player.one("loadedmetadata", () => {{
    const totalDur = player.duration();
    if (totalDur > 0) {{
      CUTS.slice(1).forEach((seg) => {{
        const marker = document.createElement("div");
        marker.className = "vjs-chapter-marker";
        marker.style.left = `${{(seg.start_time / totalDur) * 100}}%`;
        seekBar.el().appendChild(marker);
      }});
    }}
  }});

  progressControl.el().addEventListener("mousemove", (e) => {{
    const rect = seekBar.el().getBoundingClientRect();
    if (!rect.width) return;

    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const duration = player.duration() || CUTS[CUTS.length - 1].end_time;
    const hoverTime = ratio * duration;

    setCellSpriteFrame(spriteTip, hoverTime);

    const halfW = 96;
    const rawX = ratio * rect.width;
    const clampedX = Math.max(halfW, Math.min(rect.width - halfW, rawX));
    spriteTip.style.left = `${{clampedX}}px`;
  }});
}});

player.on("timeupdate", () => {{
  const t = player.currentTime();
  const idx = CUTS.findIndex((c) => t >= c.start_time && t < c.end_time);
  if (idx !== -1 && idx !== currentIndex) {{
    currentIndex = idx;
    const item = CUTS[idx];
    nowBadge.textContent = "#" + item.id;
    nowTitle.textContent = item.title;
    nowRange.textContent = item.source_range + " (" + item.duration_str + ")";
    highlightActiveCard();
  }}
}});

function openAt(index, seekTime) {{
  if (index < 0 || index >= CUTS.length) return;
  const item = CUTS[index];
  currentIndex = index;

  nowBadge.textContent = "#" + item.id;
  nowTitle.textContent = item.title;
  nowRange.textContent = item.source_range + " (" + item.duration_str + ")";
  highlightActiveCard();

  if (!popoverEl.open) {{
    popoverEl.showModal();
  }}

  if (sourceLoaded) {{
    player.currentTime(seekTime);
    player.play().catch(() => {{}});
  }} else {{
    sourceLoaded = true;
    player.src({{ type: "video/mp4", src: VIDEO_SRC }});
    player.one("loadedmetadata", () => {{
      SUBTITLES.forEach((sub) => {{
        const blob = new Blob([sub.vtt], {{ type: "text/vtt;charset=utf-8" }});
        const url = URL.createObjectURL(blob);
        const trackEl = player.addRemoteTextTrack(
          {{
            kind: "subtitles",
            label: sub.label,
            srclang: sub.srclang,
            src: url,
            default: sub.default,
          }},
          false
        );
        if (sub.default && trackEl && trackEl.track) {{
          trackEl.track.mode = "showing";
        }}
      }});
      player.currentTime(seekTime);
      player.play().catch(() => {{}});
    }});
  }}
}}

popoverEl.addEventListener("close", () => {{
  player.pause();
}});

popoverEl.addEventListener("click", (e) => {{
  if (e.target === popoverEl) {{
    popoverEl.close();
  }}
}});

closeBtn.addEventListener("click", () => {{
  popoverEl.close();
}});

document.addEventListener("keydown", (e) => {{
  if (!popoverEl.open) return;
  if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
  const step = e.shiftKey ? 10 : 5;
  if (e.key === "ArrowRight") {{
    e.preventDefault();
    player.currentTime(Math.min(player.duration() || Infinity, player.currentTime() + step));
  }} else if (e.key === "ArrowLeft") {{
    e.preventDefault();
    player.currentTime(Math.max(0, player.currentTime() - step));
  }} else if (e.key === "ArrowUp") {{
    e.preventDefault();
    player.volume(Math.min(1, player.volume() + 0.1));
  }} else if (e.key === "ArrowDown") {{
    e.preventDefault();
    player.volume(Math.max(0, player.volume() - 0.1));
  }} else if (e.key === " " || e.key === "k") {{
    e.preventDefault();
    if (player.paused()) player.play().catch(() => {{}});
    else player.pause();
  }} else if (e.key === "f") {{
    e.preventDefault();
    if (player.isFullscreen()) player.exitFullscreen();
    else player.requestFullscreen();
  }} else if (e.key === "m") {{
    e.preventDefault();
    player.muted(!player.muted());
  }}
}});

function highlightActiveCard() {{
  document.querySelectorAll(".card").forEach((el) => {{
    el.classList.toggle("active", Number(el.dataset.index) === currentIndex);
  }});
}}

function matchesFilter(item) {{
  if (!searchQuery) return true;
  const q = searchQuery.toLowerCase();
  return (
    item.id.toLowerCase().includes(q) ||
    item.title.toLowerCase().includes(q) ||
    item.source_range.toLowerCase().includes(q)
  );
}}

function renderGallery() {{
  gallery.innerHTML = "";
  let visibleCount = 0;

  CUTS.forEach((item, index) => {{
    if (!matchesFilter(item)) return;
    visibleCount++;

    const card = document.createElement("article");
    card.className = "card" + (index === currentIndex ? " active" : "");
    card.dataset.index = index;

    const grid = document.createElement("div");
    grid.className = "contact-grid";

    for (let cellIdx = 0; cellIdx < 9; cellIdx++) {{
      const slot = CELL_TO_SLOT[cellIdx];
      if (slot === -1) {{
        const center = document.createElement("div");
        center.className = "grid-cell center-cell";
        center.innerHTML = `
          <div class="center-badge">SCENE #${{item.id}}</div>
          <div class="center-title">${{item.title}}</div>
          <div class="center-range">[${{item.source_range}}]</div>
          <div class="center-dur">${{item.duration_str}}</div>
        `;
        center.addEventListener("click", (e) => {{
          e.stopPropagation();
          openAt(index, item.start_time);
        }});
        grid.appendChild(center);
      }} else {{
        const baseTime = item.cell_times[slot];
        const cell = document.createElement("div");
        cell.className = "grid-cell";
        setCellSpriteFrame(cell, baseTime);

        const timeBadge = document.createElement("span");
        timeBadge.className = "cell-time";
        timeBadge.textContent = fmtHmsMs(baseTime);
        cell.appendChild(timeBadge);

        let cellVideo = null;
        let rafId = null;

        cell.addEventListener("mouseenter", () => {{
          if (cellVideo) return;
          cellVideo = document.createElement("video");
          cellVideo.src = VIDEO_SRC;
          cellVideo.muted = true;
          cellVideo.playsInline = true;
          cellVideo.preload = "auto";
          cellVideo.addEventListener("loadedmetadata", () => {{
            if (!cellVideo) return;
            cellVideo.currentTime = baseTime;
            cellVideo.play().catch(() => {{}});
          }});
          const tick = () => {{
            if (!cellVideo) return;
            const ct = cellVideo.currentTime;
            if (ct >= baseTime + item.card_dur) {{
              cellVideo.currentTime = baseTime;
            }}
            timeBadge.textContent = fmtHmsMs(ct || baseTime);
            rafId = requestAnimationFrame(tick);
          }};
          rafId = requestAnimationFrame(tick);
          cell.insertBefore(cellVideo, timeBadge);
        }});

        cell.addEventListener("mouseleave", () => {{
          if (rafId) cancelAnimationFrame(rafId);
          rafId = null;
          if (cellVideo) {{
            cellVideo.pause();
            cellVideo.removeAttribute("src");
            cellVideo.load();
            cellVideo.remove();
            cellVideo = null;
          }}
          timeBadge.textContent = fmtHmsMs(baseTime);
        }});

        cell.addEventListener("click", (e) => {{
          e.stopPropagation();
          openAt(index, baseTime);
        }});

        grid.appendChild(cell);
      }}
    }}

    const body = document.createElement("div");
    body.className = "card-body";
    body.addEventListener("click", () => {{
      openAt(index, item.start_time);
    }});

    const idSpan = document.createElement("span");
    idSpan.className = "card-id";
    idSpan.textContent = "#" + item.id + " · " + item.title;

    const metaSpan = document.createElement("span");
    metaSpan.className = "card-meta";
    metaSpan.textContent = item.source_range + " (" + item.duration_str + ")";

    body.appendChild(idSpan);
    body.appendChild(metaSpan);

    card.appendChild(grid);
    card.appendChild(body);
    gallery.appendChild(card);
  }});

  countLabel.textContent = visibleCount + " / " + CUTS.length + " scenes";
}}

searchInput.addEventListener("input", (e) => {{
  searchQuery = e.target.value.trim();
  renderGallery();
}});

document.querySelectorAll(".view-btn").forEach((btn) => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".view-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    gallery.classList.toggle("list-view", btn.dataset.view === "list");
  }});
}});

renderGallery();
</script>
</body>
</html>
"""
    index_path = out_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path
