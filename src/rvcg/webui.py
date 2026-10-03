import json

from rvcg.models import BoundaryConfig


def render_webui_html(default_dir: str, default_config: BoundaryConfig, initial_video: str | None = None) -> str:
    cfg_json = json.dumps(
        {
            "min_seg": default_config.min_seg,
            "max_seg": default_config.max_seg,
            "target_seg": default_config.target_seg,
            "workers": default_config.workers,
            "threshold": default_config.scene_threshold,
            "title_template": default_config.title_template,
        }
    )
    init_dir_json = json.dumps(default_dir)
    init_vid_json = json.dumps(initial_video)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RapidVideoChapterGenerator</title>
<link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
<style>
  :root {{
    --bg: #0b0c10;
    --panel: #12141c;
    --panel-alt: #181b26;
    --border: #232736;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --success: #10b981;
    --danger: #ef4444;
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
    max-width: 1760px;
    margin: 0 auto;
    padding: 16px 24px 48px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}
  .toolbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
  }}
  .toolbar-left, .toolbar-right {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .brand {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.01em;
    margin-right: 6px;
  }}
  .search-input, .text-input {{
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 7px 11px;
    font-size: 12.5px;
    outline: none;
  }}
  .search-input {{
    min-width: 220px;
  }}
  .search-input:focus, .text-input:focus, select:focus {{
    border-color: var(--accent);
  }}
  select {{
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 12px;
    outline: none;
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
  button.primary {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }}
  button.primary:hover {{
    background: var(--accent-hover);
  }}
  button.success {{
    background: var(--success);
    border-color: var(--success);
    color: #fff;
  }}
  button.danger:hover {{
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
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
  }}
  .drawer-panel {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .drawer-panel.hidden {{
    display: none;
  }}
  .drawer-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }}
  .field-group {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }}
  .field-group input {{
    width: 78px;
  }}
  .file-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 8px;
    max-height: 280px;
    overflow-y: auto;
  }}
  .file-item {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    background: var(--panel-alt);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 11px;
    cursor: pointer;
    font-size: 12.5px;
    text-align: left;
  }}
  .file-item:hover {{
    border-color: var(--accent);
  }}
  .file-name {{
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }}
  .file-meta {{
    font-size: 11px;
    color: var(--muted);
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }}
  .progress-box {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .progress-box.hidden {{
    display: none;
  }}
  .phase-row {{
    display: grid;
    grid-template-columns: 230px 1fr 54px 260px;
    gap: 12px;
    align-items: center;
    font-size: 12px;
    font-family: Menlo, Monaco, monospace;
  }}
  .phase-bar-bg {{
    height: 8px;
    background: #1e2333;
    border-radius: 4px;
    overflow: hidden;
  }}
  .phase-bar-fill {{
    height: 100%;
    background: var(--accent);
    width: 0%;
    transition: width 0.15s ease;
  }}
  .phase-info {{
    color: #38bdf8;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .gallery {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 0;
  }}
  .card {{
    background: #000;
    border: 1.5px solid #2e3448;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    filter: brightness(0.68);
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
    width: 240px;
    flex-shrink: 0;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    gap: 6px;
    border-right: 1px solid var(--border);
    padding: 12px 14px;
    order: -1;
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
  .center-top {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .center-badge {{
    font-family: Menlo, monospace;
    font-size: 10px;
    font-weight: 700;
    color: var(--accent);
  }}
  .center-del {{
    padding: 0 5px;
    font-size: 10px;
    line-height: 1.3;
    background: transparent;
    color: var(--muted);
    border: 1px solid transparent;
  }}
  .center-del:hover {{
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
  }}
  .center-title-input {{
    background: transparent;
    border: 1px solid transparent;
    color: #f3f4f6;
    font-size: 11px;
    font-weight: 700;
    text-align: center;
    width: 92%;
    border-radius: 4px;
    padding: 1px 3px;
  }}
  .center-title-input:hover, .center-title-input:focus {{
    border-color: var(--border);
    background: #12141c;
    outline: none;
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
  #video-popover, #export-popover {{
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
  #export-popover {{
    width: min(88vw, 720px);
  }}
  #video-popover::backdrop, #export-popover::backdrop {{
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
  .export-textarea {{
    width: 100%;
    height: 320px;
    background: #08090d;
    color: var(--text);
    border: none;
    padding: 14px;
    font-family: Menlo, Monaco, monospace;
    font-size: 12px;
    resize: vertical;
    outline: none;
  }}
  .status-pill {{
    font-size: 11.5px;
    color: var(--success);
    font-weight: 600;
  }}
</style>
</head>
<body>
<div class="layout">
  <section class="toolbar">
    <div class="toolbar-left">
      <div class="brand" id="brand-title">RapidVideoChapterGenerator</div>
      <button type="button" id="toggle-files-btn" class="primary">Videos</button>
      <button type="button" id="toggle-settings-btn">Settings</button>
      <input id="search-input" class="search-input" type="search" placeholder="Search chapter or timestamp..." />
    </div>
    <div class="toolbar-right">
      <span id="status-pill" class="status-pill"></span>
      <span id="count-label" class="count-label"></span>
      <button type="button" id="save-chapters-btn" class="success" style="display:none;">Save Chapters (-c copy)</button>
      <button type="button" id="export-yt-btn">YouTube</button>
      <button type="button" id="export-json-btn">JSON</button>
      <button type="button" class="view-btn active" data-view="grid">Grid</button>
      <button type="button" class="view-btn" data-view="list">List</button>
    </div>
  </section>

  <section id="files-drawer" class="drawer-panel">
    <div class="drawer-row">
      <button type="button" id="up-dir-btn">↑ Parent</button>
      <input id="dir-input" class="text-input" style="flex:1;" placeholder="Directory or paste/drop video file path..." />
      <button type="button" id="go-path-btn" class="primary">Open</button>
    </div>
    <div id="file-grid" class="file-grid"></div>
  </section>

  <section id="settings-drawer" class="drawer-panel hidden">
    <div class="drawer-row">
      <label class="field-group">Preset
        <select id="preset-select">
          <option value="default">default</option>
          <option value="podcast">podcast</option>
          <option value="presentation">presentation</option>
          <option value="action">action</option>
        </select>
      </label>
      <label class="field-group">Min (s)
        <input id="cfg-min" class="text-input" type="number" step="10" />
      </label>
      <label class="field-group">Max (s)
        <input id="cfg-max" class="text-input" type="number" step="10" />
      </label>
      <label class="field-group">Target (s)
        <input id="cfg-target" class="text-input" type="number" step="10" />
      </label>
      <label class="field-group">Threshold
        <input id="cfg-th" class="text-input" type="number" step="0.02" min="0.05" max="0.95" />
      </label>
      <label class="field-group">Workers
        <input id="cfg-workers" class="text-input" type="number" step="1" min="1" max="16" />
      </label>
      <button type="button" id="redetect-btn" class="primary">Re-Detect Scenes</button>
    </div>
  </section>

  <section id="progress-box" class="progress-box hidden">
    <div class="phase-row" id="p-row-1"><span>[1/5] Embedded chapter check</span><div class="phase-bar-bg"><div class="phase-bar-fill" id="p-fill-1"></div></div><span id="p-pct-1">0%</span><span class="phase-info" id="p-info-1">waiting...</span></div>
    <div class="phase-row" id="p-row-2"><span>[2/5] Keyframe visual scan</span><div class="phase-bar-bg"><div class="phase-bar-fill" id="p-fill-2"></div></div><span id="p-pct-2">0%</span><span class="phase-info" id="p-info-2">waiting...</span></div>
    <div class="phase-row" id="p-row-3"><span>[3/5] Priority anchor placement</span><div class="phase-bar-bg"><div class="phase-bar-fill" id="p-fill-3"></div></div><span id="p-pct-3">0%</span><span class="phase-info" id="p-info-3">waiting...</span></div>
    <div class="phase-row" id="p-row-4"><span>[4/5] Long-segment subdivision</span><div class="phase-bar-bg"><div class="phase-bar-fill" id="p-fill-4"></div></div><span id="p-pct-4">0%</span><span class="phase-info" id="p-info-4">waiting...</span></div>
    <div class="phase-row" id="p-row-5"><span>[5/5] Tail merge & chapter mux</span><div class="phase-bar-bg"><div class="phase-bar-fill" id="p-fill-5"></div></div><span id="p-pct-5">0%</span><span class="phase-info" id="p-info-5">waiting...</span></div>
    <div class="phase-row" id="p-row-spr"><span>      Timeline sprite sheet</span><div class="phase-bar-bg"><div class="phase-bar-fill" id="p-fill-spr"></div></div><span id="p-pct-spr">0%</span><span class="phase-info" id="p-info-spr">rendering...</span></div>
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
    <div class="toolbar-right">
      <button id="split-here-btn" class="primary" type="button">✂ Split Chapter Here</button>
      <button id="close-popover" type="button">✕</button>
    </div>
  </div>
  <div class="player-stage">
    <video id="vjs-player" class="video-js vjs-big-play-centered" controls playsinline preload="metadata"></video>
  </div>
</dialog>

<dialog id="export-popover">
  <div class="popover-header">
    <span id="export-title" class="popover-title">Export Chapters</span>
    <div class="toolbar-right">
      <button id="copy-export-btn" class="primary" type="button">Copy</button>
      <button id="close-export" type="button">✕</button>
    </div>
  </div>
  <textarea id="export-textarea" class="export-textarea" readonly></textarea>
</dialog>

<script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
<script>
const DEFAULT_CFG = {cfg_json};
let currentDir = {init_dir_json};
let currentVideoPath = {init_vid_json};
let VIDEO_SRC = "";
let SPRITE = {{ url: "", interval: 10, cols: 10, rows: 1, total_frames: 1 }};
let CUTS = [];
let SUBTITLES = [];
let currentIndex = -1;
let searchQuery = "";
let sourceLoaded = false;

const CELL_TO_SLOT = [0, 1, 2, 3, -1, 4, 5, 6, 7];

const filesDrawer = document.getElementById("files-drawer");
const settingsDrawer = document.getElementById("settings-drawer");
const progressBox = document.getElementById("progress-box");
const fileGrid = document.getElementById("file-grid");
const dirInput = document.getElementById("dir-input");
const brandTitle = document.getElementById("brand-title");
const statusPill = document.getElementById("status-pill");
const saveChaptersBtn = document.getElementById("save-chapters-btn");
const gallery = document.getElementById("gallery");
const countLabel = document.getElementById("count-label");
const popoverEl = document.getElementById("video-popover");
const exportPopover = document.getElementById("export-popover");
const exportTextarea = document.getElementById("export-textarea");
const nowBadge = document.getElementById("now-badge");
const nowTitle = document.getElementById("now-title");
const nowRange = document.getElementById("now-range");

document.getElementById("cfg-min").value = DEFAULT_CFG.min_seg;
document.getElementById("cfg-max").value = DEFAULT_CFG.max_seg;
document.getElementById("cfg-target").value = DEFAULT_CFG.target_seg;
document.getElementById("cfg-th").value = DEFAULT_CFG.threshold;
document.getElementById("cfg-workers").value = DEFAULT_CFG.workers;

document.getElementById("preset-select").addEventListener("change", (e) => {{
  const p = e.target.value;
  if (p === "podcast") {{
    document.getElementById("cfg-min").value = 120;
    document.getElementById("cfg-max").value = 900;
    document.getElementById("cfg-target").value = 450;
    document.getElementById("cfg-th").value = 0.45;
  }} else if (p === "presentation") {{
    document.getElementById("cfg-min").value = 60;
    document.getElementById("cfg-max").value = 600;
    document.getElementById("cfg-target").value = 300;
    document.getElementById("cfg-th").value = 0.30;
  }} else if (p === "action") {{
    document.getElementById("cfg-min").value = 90;
    document.getElementById("cfg-max").value = 420;
    document.getElementById("cfg-target").value = 240;
    document.getElementById("cfg-th").value = 0.35;
  }} else {{
    document.getElementById("cfg-min").value = 180;
    document.getElementById("cfg-max").value = 600;
    document.getElementById("cfg-target").value = 360;
    document.getElementById("cfg-th").value = 0.38;
  }}
}});

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
  if (!SPRITE.url) return;
  const frameIdx = Math.max(0, Math.min(SPRITE.total_frames - 1, Math.floor(timeSec / SPRITE.interval)));
  const col = frameIdx % SPRITE.cols;
  const row = Math.floor(frameIdx / SPRITE.cols);
  const xPct = SPRITE.cols > 1 ? (col / (SPRITE.cols - 1)) * 100 : 0;
  const yPct = SPRITE.rows > 1 ? (row / (SPRITE.rows - 1)) * 100 : 0;
  el.style.backgroundImage = `url("${{SPRITE.url}}")`;
  el.style.backgroundSize = `${{SPRITE.cols * 100}}% ${{SPRITE.rows * 100}}%`;
  el.style.backgroundPosition = `${{xPct.toFixed(3)}}% ${{yPct.toFixed(3)}}%`;
}}

function refreshSeekbarMarkers() {{
  const seekBar = player.controlBar.progressControl.seekBar;
  seekBar.el().querySelectorAll(".vjs-chapter-marker").forEach((m) => m.remove());
  const totalDur = player.duration() || (CUTS.length ? CUTS[CUTS.length - 1].end_time : 0);
  if (totalDur > 0) {{
    CUTS.slice(1).forEach((seg) => {{
      const marker = document.createElement("div");
      marker.className = "vjs-chapter-marker";
      marker.style.left = `${{(seg.start_time / totalDur) * 100}}%`;
      seekBar.el().appendChild(marker);
    }});
  }}
}}

player.ready(() => {{
  const progressControl = player.controlBar.progressControl;
  const seekBar = progressControl.seekBar;

  const spriteTip = document.createElement("div");
  spriteTip.className = "vjs-sprite-tooltip";
  seekBar.el().appendChild(spriteTip);

  player.on("loadedmetadata", () => {{
    refreshSeekbarMarkers();
  }});

  progressControl.el().addEventListener("mousemove", (e) => {{
    const rect = seekBar.el().getBoundingClientRect();
    if (!rect.width || !CUTS.length) return;

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

async function loadDirectory(dirPath) {{
  const res = await fetch(`/api/fs?dir=${{encodeURIComponent(dirPath || "")}}`);
  const data = await res.json();
  if (!data.ok) return;
  currentDir = data.dir;
  dirInput.value = currentDir;
  fileGrid.innerHTML = "";

  data.dirs.forEach((d) => {{
    const btn = document.createElement("button");
    btn.className = "file-item";
    btn.innerHTML = `<span class="file-name">📁 ${{d.name}}</span><span class="file-meta">Folder</span>`;
    btn.addEventListener("click", () => loadDirectory(d.path));
    fileGrid.appendChild(btn);
  }});

  data.videos.forEach((v) => {{
    const btn = document.createElement("button");
    btn.className = "file-item";
    btn.innerHTML = `<span class="file-name">🎬 ${{v.name}}</span><span class="file-meta">${{v.size_mb}} MB</span>`;
    btn.addEventListener("click", () => startScan(v.path, false));
    fileGrid.appendChild(btn);
  }});
}}

function setPhaseUI(id, pct, info) {{
  const fill = document.getElementById(`p-fill-${{id}}`);
  const pctEl = document.getElementById(`p-pct-${{id}}`);
  const infoEl = document.getElementById(`p-info-${{id}}`);
  if (fill) fill.style.width = `${{Math.max(0, Math.min(100, pct))}}%`;
  if (pctEl) pctEl.textContent = `${{Math.round(pct)}}%`;
  if (infoEl && info !== undefined) infoEl.textContent = info;
}}

async function startScan(videoPath, forceRefresh) {{
  currentVideoPath = videoPath;
  filesDrawer.classList.add("hidden");
  progressBox.classList.remove("hidden");
  statusPill.textContent = "Scanning...";
  for (let i = 1; i <= 5; i++) setPhaseUI(i, 0, "waiting...");
  setPhaseUI("spr", 0, "rendering...");

  const payload = {{
    path: videoPath,
    refresh: Boolean(forceRefresh),
    min_seg: Number(document.getElementById("cfg-min").value || 180),
    max_seg: Number(document.getElementById("cfg-max").value || 600),
    target_seg: Number(document.getElementById("cfg-target").value || 360),
    threshold: Number(document.getElementById("cfg-th").value || 0.38),
    workers: Number(document.getElementById("cfg-workers").value || 8),
  }};

  const res = await fetch("/api/scan", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(payload),
  }});
  const startData = await res.json();
  if (!startData.ok) {{
    statusPill.textContent = "Error: " + (startData.error || "failed");
    return;
  }}

  const es = new EventSource(`/api/jobs/${{startData.job_id}}/events`);
  es.onmessage = (ev) => {{
    const msg = JSON.parse(ev.data);
    if (msg.type === "phase") {{
      const pct = msg.total > 0 ? (msg.completed / msg.total) * 100 : 100;
      setPhaseUI(msg.phase, pct, msg.info);
    }} else if (msg.type === "sprite") {{
      const pct = msg.total > 0 ? (msg.completed / msg.total) * 100 : 100;
      setPhaseUI("spr", pct, msg.info || "rendering...");
    }} else if (msg.type === "complete") {{
      es.close();
      progressBox.classList.add("hidden");
      VIDEO_SRC = `/api/media?path=${{encodeURIComponent(msg.video_path)}}`;
      SPRITE = msg.sprite;
      CUTS = msg.chapters;
      SUBTITLES = msg.subtitles || [];
      sourceLoaded = false;
      brandTitle.textContent = msg.video_name;
      statusPill.textContent = `✓ ${{CUTS.length}} chapters ready`;
      saveChaptersBtn.style.display = "none";
      renderGallery();
    }} else if (msg.type === "error") {{
      es.close();
      statusPill.textContent = "Error: " + msg.error;
    }}
  }};
}}

async function syncChaptersEdit(rawChapters) {{
  const res = await fetch("/api/chapters/recalc", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ chapters: rawChapters }}),
  }});
  const data = await res.json();
  if (data.ok) {{
    CUTS = data.chapters;
    saveChaptersBtn.style.display = "inline-flex";
    statusPill.textContent = "Unsaved chapter edits";
    renderGallery();
    refreshSeekbarMarkers();
  }}
}}

async function saveChaptersToVideo() {{
  if (!currentVideoPath || !CUTS.length) return;
  statusPill.textContent = "Saving (-c copy)...";
  const res = await fetch("/api/chapters/save", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ path: currentVideoPath, chapters: CUTS }}),
  }});
  const data = await res.json();
  if (data.ok) {{
    saveChaptersBtn.style.display = "none";
    statusPill.textContent = `✓ Saved ${{CUTS.length}} chapters to video`;
  }} else {{
    statusPill.textContent = "Save failed: " + (data.error || "");
  }}
}}

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
      refreshSeekbarMarkers();
      player.currentTime(seekTime);
      player.play().catch(() => {{}});
    }});
  }}
}}

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

        const topRow = document.createElement("div");
        topRow.className = "center-top";
        const badge = document.createElement("span");
        badge.className = "center-badge";
        badge.textContent = `SCENE #${{item.id}}`;
        topRow.appendChild(badge);

        if (CUTS.length > 1) {{
          const delBtn = document.createElement("button");
          delBtn.className = "center-del";
          delBtn.type = "button";
          delBtn.textContent = "×";
          delBtn.addEventListener("click", (e) => {{
            e.stopPropagation();
            const next = CUTS.map((c) => ({{ start_time: c.start_time, end_time: c.end_time, title: c.title }}));
            if (index === 0) {{
              next[1].start_time = next[0].start_time;
            }} else {{
              next[index - 1].end_time = next[index].end_time;
            }}
            next.splice(index, 1);
            syncChaptersEdit(next);
          }});
          topRow.appendChild(delBtn);
        }}

        const titleInput = document.createElement("input");
        titleInput.className = "center-title-input";
        titleInput.value = item.title;
        titleInput.addEventListener("click", (e) => e.stopPropagation());
        titleInput.addEventListener("change", () => {{
          const next = CUTS.map((c, idx) => ({{
            start_time: c.start_time,
            end_time: c.end_time,
            title: idx === index ? titleInput.value : c.title,
          }}));
          syncChaptersEdit(next);
        }});

        const rangeEl = document.createElement("div");
        rangeEl.className = "center-range";
        rangeEl.textContent = `[${{item.source_range}}]`;

        const durEl = document.createElement("div");
        durEl.className = "center-dur";
        durEl.textContent = item.duration_str;

        center.appendChild(topRow);
        center.appendChild(titleInput);
        center.appendChild(rangeEl);
        center.appendChild(durEl);

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
          if (cellVideo || !VIDEO_SRC) return;
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
    body.addEventListener("click", () => openAt(index, item.start_time));

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

  countLabel.textContent = visibleCount + " / " + CUTS.length + " chapters";
}}

document.getElementById("toggle-files-btn").addEventListener("click", () => {{
  filesDrawer.classList.toggle("hidden");
}});

document.getElementById("toggle-settings-btn").addEventListener("click", () => {{
  settingsDrawer.classList.toggle("hidden");
}});

document.getElementById("up-dir-btn").addEventListener("click", async () => {{
  const res = await fetch(`/api/fs?dir=${{encodeURIComponent(currentDir)}}&parent=1`);
  const data = await res.json();
  if (data.ok) loadDirectory(data.dir);
}});

document.getElementById("go-path-btn").addEventListener("click", async () => {{
  const raw = dirInput.value.trim();
  if (!raw) return;
  const res = await fetch("/api/resolve-path", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ path: raw }}),
  }});
  const data = await res.json();
  if (data.ok && data.kind === "file") {{
    startScan(data.path, false);
  }} else if (data.ok && data.kind === "dir") {{
    loadDirectory(data.path);
  }} else {{
    statusPill.textContent = "Path not found";
  }}
}});

document.getElementById("redetect-btn").addEventListener("click", () => {{
  if (currentVideoPath) startScan(currentVideoPath, true);
}});

saveChaptersBtn.addEventListener("click", () => saveChaptersToVideo());

document.getElementById("split-here-btn").addEventListener("click", () => {{
  const t = Math.round(player.currentTime() * 100) / 100;
  const idx = CUTS.findIndex((c) => t > c.start_time + 2 && t < c.end_time - 2);
  if (idx === -1) return;
  const next = CUTS.map((c) => ({{ start_time: c.start_time, end_time: c.end_time, title: c.title }}));
  const origEnd = next[idx].end_time;
  next[idx].end_time = t;
  next.splice(idx + 1, 0, {{
    start_time: t,
    end_time: origEnd,
    title: `Scene ${{String(idx + 2).padStart(2, "0")}}`,
  }});
  syncChaptersEdit(next);
}});

async function showExport(fmt) {{
  if (!CUTS.length) return;
  const res = await fetch("/api/chapters/export", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ format: fmt, chapters: CUTS }}),
  }});
  const data = await res.json();
  if (data.ok) {{
    document.getElementById("export-title").textContent = `Export (${{fmt.toUpperCase()}})`;
    exportTextarea.value = data.content;
    exportPopover.showModal();
  }}
}}

document.getElementById("export-yt-btn").addEventListener("click", () => showExport("youtube"));
document.getElementById("export-json-btn").addEventListener("click", () => showExport("json"));
document.getElementById("copy-export-btn").addEventListener("click", () => {{
  navigator.clipboard.writeText(exportTextarea.value);
}});
document.getElementById("close-export").addEventListener("click", () => exportPopover.close());

popoverEl.addEventListener("close", () => player.pause());
popoverEl.addEventListener("click", (e) => {{
  if (e.target === popoverEl) popoverEl.close();
}});
document.getElementById("close-popover").addEventListener("click", () => popoverEl.close());

document.getElementById("search-input").addEventListener("input", (e) => {{
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

loadDirectory(currentDir).then(() => {{
  if (currentVideoPath) startScan(currentVideoPath, false);
}});
</script>
</body>
</html>
"""
