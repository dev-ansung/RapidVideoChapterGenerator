export const state = {
  currentDir: "",
  currentVideoPath: "",
  videoSrc: "",
  sprite: { url: "", interval: 10, cols: 10, rows: 1, total_frames: 1 },
  cuts: [],
  rawCandidates: [],
  subtitles: [],
  currentIndex: -1,
  searchQuery: "",
  sourceLoaded: false,
  lastStats: null,
  winState: { x: null, y: null, w: 720 },
  manualPlayheadRef: 0,
  manualPathTouched: false,
};

export function initStateFromBoot() {
  if (window.__RVCG_BOOT__) {
    if (window.__RVCG_BOOT__.initDir) state.currentDir = window.__RVCG_BOOT__.initDir;
    if (window.__RVCG_BOOT__.initVid) state.currentVideoPath = window.__RVCG_BOOT__.initVid;
  }
}

export const dom = {
  get pickerView() { return document.getElementById("picker-view"); },
  get browserView() { return document.getElementById("browser-view"); },
  get resumeBrowserBtn() { return document.getElementById("resume-browser-btn"); },
  get progressBox() { return document.getElementById("progress-box"); },
  get progressTitle() { return document.getElementById("progress-title"); },
  get progressSummary() { return document.getElementById("progress-summary"); },
  get scanLog() { return document.getElementById("scan-log"); },
  get fileGrid() { return document.getElementById("file-grid"); },
  get dirInput() { return document.getElementById("dir-input"); },
  get brandTitle() { return document.getElementById("brand-title"); },
  get statusPill() { return document.getElementById("status-pill"); },
  get revealFileBtn() { return document.getElementById("reveal-file-btn"); },
  get saveChaptersBtn() { return document.getElementById("save-chapters-btn"); },
  get gallery() { return document.getElementById("gallery"); },
  get countLabel() { return document.getElementById("count-label"); },
  get playerShell() { return document.getElementById("player-shell"); },
  get nowBadge() { return document.getElementById("now-badge"); },
  get nowTitle() { return document.getElementById("now-title"); },
  get nowRange() { return document.getElementById("now-range"); },
  get exportPopover() { return document.getElementById("export-popover"); },
  get exportTitle() { return document.getElementById("export-title"); },
  get exportTextarea() { return document.getElementById("export-textarea"); },
  get exportDropdown() { return document.getElementById("export-dropdown"); },
  get exportSceneBtn() { return document.getElementById("export-scene-btn"); },
  get splitModalPopover() { return document.getElementById("split-modal-popover"); },
  get splitTargetBadge() { return document.getElementById("split-target-badge"); },
  get splitPrevHero() { return document.getElementById("split-prev-hero"); },
  get splitCenterHero() { return document.getElementById("split-center-hero"); },
  get splitNextHero() { return document.getElementById("split-next-hero"); },
  get splitCenterTimeLabel() { return document.getElementById("split-center-time-label"); },
  get splitRibbonCands() { return document.getElementById("split-ribbon-cands"); },
  get splitPrevCutBtn() { return document.getElementById("split-prev-cut-btn"); },
  get splitNextCutBtn() { return document.getElementById("split-next-cut-btn"); },
  get splitTimeInput() { return document.getElementById("split-time-input"); },
  get splitThumb() { return document.getElementById("split-thumb"); },
  get splitUsePlayheadBtn() { return document.getElementById("split-use-playhead-btn"); },
  get splitPreviewBtn() { return document.getElementById("split-preview-btn"); },
  get splitPropLeft() { return document.getElementById("split-prop-left"); },
  get splitPropRight() { return document.getElementById("split-prop-right"); },
  get splitLeftLabel() { return document.getElementById("split-left-label"); },
  get splitRightLabel() { return document.getElementById("split-right-label"); },
  get confirmSplitBtn() { return document.getElementById("confirm-split-btn"); },
  get cancelSplitBtn() { return document.getElementById("cancel-split-btn"); },
  get closeSplitModal() { return document.getElementById("close-split-modal"); },
  get settingsPopover() { return document.getElementById("settings-popover"); },
  get prefShowCutDot() { return document.getElementById("pref-show-cut-dot"); },
  get cfgMin() { return document.getElementById("cfg-min"); },
  get cfgMax() { return document.getElementById("cfg-max"); },
  get cfgTarget() { return document.getElementById("cfg-target"); },
  get cfgTh() { return document.getElementById("cfg-th"); },
  get cfgBlackDur() { return document.getElementById("cfg-black-dur"); },
  get cfgEnableBlack() { return document.getElementById("cfg-enable-black"); },
  get cfgEnableVisual() { return document.getElementById("cfg-enable-visual"); },
  get cfgEnableSub() { return document.getElementById("cfg-enable-sub"); },
  get cfgWorkers() { return document.getElementById("cfg-workers"); },
  get statBlack() { return document.getElementById("stat-black"); },
  get statVisual() { return document.getElementById("stat-visual"); },
  get statSub() { return document.getElementById("stat-sub"); },
};

export function fmtHms(sec) {
  const s = Math.max(0, Math.floor(sec));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return (
    String(hh).padStart(2, "0") + ":" +
    String(mm).padStart(2, "0") + ":" +
    String(ss).padStart(2, "0")
  );
}

export function fmtHmsMs(sec) {
  const s = Math.max(0, sec);
  const ms = Math.floor((s - Math.floor(s)) * 1000);
  return fmtHms(s) + "." + String(ms).padStart(3, "0");
}

export function parseTimeInput(raw) {
  const s = String(raw || "").trim();
  if (!s) return NaN;
  if (/^\d+(\.\d+)?$/.test(s)) return Number(s);
  const parts = s.split(":").map(Number);
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return NaN;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return NaN;
}

export function formatMechanismSummary(stats) {
  if (!stats) return "";
  return `${stats.used_black} black · ${stats.used_visual} visual · +${stats.sub_cuts} subdiv`;
}

export function setCellSpriteFrame(el, timeSec) {
  if (!state.sprite.url) return;
  const frameIdx = Math.max(0, Math.min(state.sprite.total_frames - 1, Math.floor(timeSec / state.sprite.interval)));
  const col = frameIdx % state.sprite.cols;
  const row = Math.floor(frameIdx / state.sprite.cols);
  const xPct = state.sprite.cols > 1 ? (col / (state.sprite.cols - 1)) * 100 : 0;
  const yPct = state.sprite.rows > 1 ? (row / (state.sprite.rows - 1)) * 100 : 0;
  el.style.backgroundImage = `url("${state.sprite.url}")`;
  el.style.backgroundSize = `${state.sprite.cols * 100}% ${state.sprite.rows * 100}%`;
  el.style.backgroundPosition = `${xPct.toFixed(3)}% ${yPct.toFixed(3)}%`;
}

export function cutDotColorClass(kind) {
  switch (kind) {
    case "black":
      return "bg-base-content/40";
    case "visual":
      return "bg-base-content";
    case "subdivide":
      return "bg-info";
    case "manual":
      return "bg-warning";
    default:
      return "bg-success";
  }
}
