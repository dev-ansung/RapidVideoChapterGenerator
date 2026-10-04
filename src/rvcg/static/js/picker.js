import { state, dom, formatMechanismSummary } from "./state.js";
import { fetchFs, resolvePath, startScanJob, setStatus } from "./api.js";
import { renderGallery } from "./gallery.js";
import { saveSettingsToLocalStorage } from "./settings.js";

export function showView(viewName) {
  if (viewName === "browser") {
    dom.pickerView?.classList.add("hidden");
    dom.browserView?.classList.remove("hidden");
    dom.resumeBrowserBtn?.classList.remove("hidden");
  } else {
    dom.browserView?.classList.add("hidden");
    dom.pickerView?.classList.remove("hidden");
  }
}

export function syncStageUI() {
  const bOn = dom.cfgEnableBlack?.checked;
  const wOn = bOn && dom.cfgEnableWhite?.checked;
  const vOn = dom.cfgEnableVisual?.checked;
  const sOn = dom.cfgEnableSub?.checked;

  document.getElementById("stage-black")?.classList.toggle("opacity-50", !bOn);
  if (dom.cfgBlackDur) dom.cfgBlackDur.disabled = !bOn;
  if (dom.cfgBlackPicTh) dom.cfgBlackPicTh.disabled = !bOn;
  if (dom.cfgBlackPixTh) dom.cfgBlackPixTh.disabled = !bOn;
  if (dom.cfgEnableWhite) dom.cfgEnableWhite.disabled = !bOn;
  if (dom.cfgWhitePicTh) dom.cfgWhitePicTh.disabled = !wOn;
  if (dom.cfgWhitePixTh) dom.cfgWhitePixTh.disabled = !wOn;

  document.getElementById("stage-visual")?.classList.toggle("opacity-50", !vOn);
  if (dom.cfgTh) dom.cfgTh.disabled = !vOn;

  document.getElementById("stage-subdivide")?.classList.toggle("opacity-50", !sOn);
  if (dom.cfgMax) dom.cfgMax.disabled = !sOn;
  if (dom.cfgTarget) dom.cfgTarget.disabled = !sOn;
}

export function appendScanLog(line) {
  if (!dom.scanLog) return;
  dom.scanLog.value += (dom.scanLog.value ? "\n" : "") + line;
  dom.scanLog.scrollTop = dom.scanLog.scrollHeight;
}

export function setPhaseUI(id, pct, info) {
  const fill = document.getElementById(`p-fill-${id}`);
  const pctEl = document.getElementById(`p-pct-${id}`);
  const infoEl = document.getElementById(`p-info-${id}`);
  if (fill) fill.value = Math.max(0, Math.min(100, pct));
  if (pctEl) {
    const displayPct = pct >= 100 ? 100 : Math.min(99, Math.floor(pct));
    pctEl.textContent = `${displayPct}%`;
  }
  if (infoEl && info !== undefined) {
    infoEl.textContent = info;
    infoEl.dataset.tippyContent = info;
    if (infoEl._tippy) {
      infoEl._tippy.setContent(info);
    } else if (typeof window.tippy !== "undefined") {
      window.tippy(infoEl, {
        placement: "top",
        delay: [60, 0],
        maxWidth: 460,
        appendTo: () => document.body,
      });
    }
  }
}

export async function loadDirectory(dirPath) {
  const data = await fetchFs(dirPath);
  if (!data.ok) return;
  state.currentDir = data.dir;
  if (dom.dirInput) dom.dirInput.value = state.currentDir;
  if (!dom.fileGrid) return;
  dom.fileGrid.innerHTML = "";

  data.dirs.forEach((d) => {
    const btn = document.createElement("button");
    btn.className = "file-item btn btn-outline btn-sm justify-between w-full h-auto py-2 font-normal hover:border-primary/50 transition-colors";
    btn.dataset.tippyContent = d.name;
    const nameSpan = document.createElement("span");
    nameSpan.className = "flex items-center gap-1.5 truncate mr-2 text-xs";
    nameSpan.innerHTML = `<i class="ph ph-folder text-warning text-sm shrink-0"></i><span class="truncate">${d.name}</span>`;
    const metaSpan = document.createElement("span");
    metaSpan.className = "badge badge-ghost badge-xs shrink-0 text-[10px]";
    metaSpan.textContent = "Folder";
    btn.appendChild(nameSpan);
    btn.appendChild(metaSpan);
    btn.addEventListener("click", () => loadDirectory(d.path));
    dom.fileGrid.appendChild(btn);
  });

  data.videos.forEach((v) => {
    const btn = document.createElement("button");
    btn.className = "file-item btn btn-outline btn-sm justify-between w-full h-auto py-2 font-normal hover:border-primary/50 transition-colors";
    btn.dataset.tippyContent = v.name;
    const nameSpan = document.createElement("span");
    nameSpan.className = "flex items-center gap-1.5 truncate mr-2 text-xs font-medium";
    nameSpan.innerHTML = `<i class="ph ph-film-strip text-primary text-sm shrink-0"></i><span class="truncate">${v.name}</span>`;
    const metaSpan = document.createElement("span");
    metaSpan.className = "badge badge-neutral badge-xs shrink-0 font-mono text-[10px]";
    metaSpan.textContent = `${v.size_mb} MB`;
    btn.appendChild(nameSpan);
    btn.appendChild(metaSpan);
    btn.addEventListener("click", () => startScan(v.path, false));
    dom.fileGrid.appendChild(btn);
  });

  if (typeof window.tippy !== "undefined") {
    window.tippy(dom.fileGrid.querySelectorAll(".file-item"), {
      placement: "top-start",
      delay: [60, 0],
      maxWidth: 680,
      appendTo: () => document.body,
    });
  }
}

export async function startScan(videoPath, forceRefresh, onScanComplete) {
  state.currentVideoPath = videoPath;
  const slashIdx = videoPath.lastIndexOf("/");
  const baseName = slashIdx >= 0 ? videoPath.slice(slashIdx + 1) : videoPath;
  if (slashIdx > 0) {
    const parentDir = videoPath.slice(0, slashIdx);
    if (parentDir !== state.currentDir || (dom.dirInput && dom.dirInput.value.trim() !== parentDir)) {
      loadDirectory(parentDir);
    }
  }
  showView("picker");
  dom.progressBox?.classList.remove("hidden");
  for (let i = 1; i <= 5; i++) setPhaseUI(i, 0, "waiting...");
  setPhaseUI("spr", 0, "rendering...");

  const rawWhtPix = Number(dom.cfgWhitePixTh?.value || 90);
  const payload = {
    path: videoPath,
    refresh: Boolean(forceRefresh),
    min_seg: Number(dom.cfgMin?.value || 180),
    max_seg: Number(dom.cfgMax?.value || 600),
    target_seg: Number(dom.cfgTarget?.value || 360),
    threshold: Number(dom.cfgTh?.value || 0.38),
    black_min_dur: Number(dom.cfgBlackDur?.value || 0.4),
    black_pic_th: Number(dom.cfgBlackPicTh?.value || 95) / 100.0,
    black_pix_th: Number(dom.cfgBlackPixTh?.value || 12) / 100.0,
    white_pic_th: Number(dom.cfgWhitePicTh?.value || 95) / 100.0,
    white_pix_th: Math.max(0.01, (100.0 - rawWhtPix) / 100.0),
    enable_black_fades: Boolean(dom.cfgEnableBlack?.checked),
    enable_white_fades: Boolean(dom.cfgEnableBlack?.checked && dom.cfgEnableWhite?.checked),
    enable_visual_cuts: Boolean(dom.cfgEnableVisual?.checked),
    enable_subdivide: Boolean(dom.cfgEnableSub?.checked),
    workers: Number(dom.cfgWorkers?.value || 8),
    title_template: dom.cfgTitleTemplate?.value || "Scene {n:02d}",
    card_dur: Number(dom.cfgCardDur?.value || 8.4),
  };

  state.lastStats = null;
  if (dom.progressTitle) dom.progressTitle.textContent = `Scan Diagnostics: ${baseName}`;
  if (dom.progressSummary) dom.progressSummary.textContent = "in progress...";
  if (dom.statBlack) dom.statBlack.textContent = payload.enable_black_fades ? "scanning..." : "off";
  if (dom.statVisual) dom.statVisual.textContent = payload.enable_visual_cuts ? "scanning..." : "off";
  if (dom.statSub) dom.statSub.textContent = payload.enable_subdivide ? "waiting..." : "off";
  if (dom.scanLog) dom.scanLog.value = `[Start] ${baseName} | min=${payload.min_seg}s workers=${payload.workers} | Stage1(fades)=${payload.enable_black_fades ? payload.black_min_dur + "s" : "OFF"} Stage2(visual)=${payload.enable_visual_cuts ? payload.threshold : "OFF"} Stage3(sub)=${payload.enable_subdivide ? payload.max_seg + "s->" + payload.target_seg + "s" : "OFF"}`;

  const startData = await startScanJob(payload);
  if (!startData.ok) {
    setPhaseUI(1, 0, "Error: " + (startData.error || "failed"));
    appendScanLog("[Error] " + (startData.error || "failed"));
    return;
  }

  const lastPhaseInfo = {};
  const es = new EventSource(`/api/jobs/${startData.job_id}/events`);
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "phase") {
      const pct = msg.total > 0 ? (msg.completed / msg.total) * 100 : 100;
      setPhaseUI(msg.phase, pct, msg.info);
      if (msg.phase === 2 && typeof msg.info === "string") {
        const m = msg.info.match(/(\d+)\s+black\s+·\s+(\d+)\s+white\s+·\s+(\d+)\s+visual cuts/);
        if (m) {
          const totFades = Number(m[1]) + Number(m[2]);
          if (payload.enable_black_fades && dom.statBlack) dom.statBlack.textContent = `${totFades} raw`;
          const displayPct = pct >= 100 ? 100 : Math.min(99, Math.floor(pct));
          if (dom.progressSummary) dom.progressSummary.textContent = `${displayPct}% · ${m[1]} black · ${m[2]} white · ${m[3]} visual`;
        }
      }
      if (msg.phase !== 2 && msg.info && lastPhaseInfo[msg.phase] !== msg.info) {
        lastPhaseInfo[msg.phase] = msg.info;
        appendScanLog(`[Phase ${msg.phase}] ${msg.info}`);
      }
    } else if (msg.type === "sprite") {
      const pct = msg.total > 0 ? (msg.completed / msg.total) * 100 : 100;
      setPhaseUI("spr", pct, msg.info || "rendering...");
    } else if (msg.type === "complete") {
      es.close();
      setPhaseUI("spr", 100, "sprite sheet ready");
      state.videoSrc = `/api/media?path=${encodeURIComponent(msg.video_path)}`;
      state.sprite = msg.sprite;
      state.cuts = msg.chapters;
      state.rawCandidates = Array.isArray(msg.candidates) ? msg.candidates : [];
      state.subtitles = msg.subtitles || [];
      state.lastStats = msg.stats || null;
      if (state.lastStats) {
        if (dom.statBlack) {
          const usedFades = (state.lastStats.used_black || 0) + (state.lastStats.used_white || 0);
          const rawFades = (state.lastStats.raw_black || 0) + (state.lastStats.raw_white || 0);
          const breakdown = (state.lastStats.used_white || 0) > 0 ? ` (${state.lastStats.used_black}b/${state.lastStats.used_white}w)` : "";
          dom.statBlack.textContent = payload.enable_black_fades ? `${usedFades} cuts${breakdown} (${rawFades} raw)` : `off (${rawFades} raw)`;
        }
        if (dom.statVisual) dom.statVisual.textContent = payload.enable_visual_cuts ? `${state.lastStats.used_visual} cuts (${state.lastStats.raw_visual} raw)` : `off (${state.lastStats.raw_visual} raw)`;
        const mechStr = formatMechanismSummary(state.lastStats);
        if (dom.progressSummary) dom.progressSummary.textContent = `${state.cuts.length} chapters${mechStr ? ` (${mechStr})` : ""}`;
      } else {
        if (dom.progressSummary) dom.progressSummary.textContent = `${state.cuts.length} chapters`;
      }
      if (dom.progressTitle) dom.progressTitle.textContent = `Scan Diagnostics — ${msg.video_name}`;
      if (Array.isArray(msg.logs) && msg.logs.length) {
        appendScanLog(msg.logs.join("\n"));
      }
      state.sourceLoaded = false;
      if (dom.brandTitle) dom.brandTitle.textContent = msg.video_name;
      setStatus(msg.already_embedded ? "✓ Embedded" : "Unmuxed", false);
      renderGallery();
      showView("browser");
      if (onScanComplete) onScanComplete();
    } else if (msg.type === "error") {
      es.close();
      setPhaseUI(1, 0, "Error: " + msg.error);
      if (dom.progressSummary) dom.progressSummary.textContent = "error";
      appendScanLog("[Error] " + msg.error);
    }
  };
}

export function applyPreset(presetId) {
  const presets = window.__RVCG_BOOT__?.presets || {};
  let meta = presets[presetId];
  if (!meta && (presetId === "movie" || presetId === "black-fades" || presetId === "fades")) {
    meta = presets["default"];
  } else if (!meta && presetId === "all-stages") {
    meta = presets["balanced"];
  }
  if (!meta) return;

  const cfg = meta.config;
  if (dom.cfgMin && cfg.min_seg !== undefined) dom.cfgMin.value = cfg.min_seg;
  if (dom.cfgMax && cfg.max_seg !== undefined) dom.cfgMax.value = cfg.max_seg;
  if (dom.cfgTarget && cfg.target_seg !== undefined) dom.cfgTarget.value = cfg.target_seg;
  if (dom.cfgTh && cfg.scene_threshold !== undefined) dom.cfgTh.value = cfg.scene_threshold;
  if (dom.cfgBlackDur && cfg.black_min_dur !== undefined) dom.cfgBlackDur.value = cfg.black_min_dur;
  if (dom.cfgBlackPicTh && cfg.black_pic_th !== undefined) dom.cfgBlackPicTh.value = Math.round(cfg.black_pic_th * 100);
  if (dom.cfgBlackPixTh && cfg.black_pix_th !== undefined) dom.cfgBlackPixTh.value = Math.round(cfg.black_pix_th * 100);
  if (dom.cfgWhitePicTh && cfg.white_pic_th !== undefined) dom.cfgWhitePicTh.value = Math.round(cfg.white_pic_th * 100);
  if (dom.cfgWhitePixTh && cfg.white_pix_th !== undefined) dom.cfgWhitePixTh.value = Math.round((1.0 - cfg.white_pix_th) * 100);
  if (dom.cfgEnableBlack && cfg.enable_black_fades !== undefined) dom.cfgEnableBlack.checked = cfg.enable_black_fades;
  if (dom.cfgEnableWhite && cfg.enable_white_fades !== undefined) dom.cfgEnableWhite.checked = cfg.enable_white_fades;
  if (dom.cfgEnableVisual && cfg.enable_visual_cuts !== undefined) dom.cfgEnableVisual.checked = cfg.enable_visual_cuts;
  if (dom.cfgEnableSub && cfg.enable_subdivide !== undefined) dom.cfgEnableSub.checked = cfg.enable_subdivide;

  const presetBadge = document.getElementById("preset-badge");
  if (presetBadge) presetBadge.textContent = meta.id;

  const presetDesc = document.getElementById("preset-desc");
  if (presetDesc) presetDesc.textContent = meta.description;

  const presetSelect = document.getElementById("preset-select");
  if (presetSelect && presetSelect.value !== meta.id && presetSelect.querySelector(`option[value="${meta.id}"]`)) {
    presetSelect.value = meta.id;
  }

  syncStageUI();
  saveSettingsToLocalStorage();
}

export function markPresetCustom() {
  const presetBadge = document.getElementById("preset-badge");
  if (presetBadge) presetBadge.textContent = "custom";
  const presetDesc = document.getElementById("preset-desc");
  if (presetDesc) presetDesc.textContent = "Manual configuration overrides active.";
  const presetSelect = document.getElementById("preset-select");
  if (presetSelect) {
    const customOpt = presetSelect.querySelector('option[value="custom"]');
    if (customOpt) customOpt.disabled = false;
    presetSelect.value = "custom";
  }
}

export function initPicker(onScanComplete) {
  const defaultCfg = window.__RVCG_BOOT__?.defaultCfg || {};
  if (dom.cfgMin) dom.cfgMin.value = defaultCfg.min_seg ?? 180;
  if (dom.cfgMax) dom.cfgMax.value = defaultCfg.max_seg ?? 600;
  if (dom.cfgTarget) dom.cfgTarget.value = defaultCfg.target_seg ?? 360;
  if (dom.cfgTh) dom.cfgTh.value = defaultCfg.threshold ?? 0.38;
  if (dom.cfgBlackDur) dom.cfgBlackDur.value = defaultCfg.black_min_dur ?? 0.4;
  if (dom.cfgBlackPicTh) dom.cfgBlackPicTh.value = Math.round((defaultCfg.black_pic_th ?? 0.95) * 100);
  if (dom.cfgBlackPixTh) dom.cfgBlackPixTh.value = Math.round((defaultCfg.black_pix_th ?? 0.12) * 100);
  if (dom.cfgWhitePicTh) dom.cfgWhitePicTh.value = Math.round((defaultCfg.white_pic_th ?? 0.95) * 100);
  if (dom.cfgWhitePixTh) dom.cfgWhitePixTh.value = Math.round((1.0 - (defaultCfg.white_pix_th ?? 0.10)) * 100);
  if (dom.cfgEnableBlack) dom.cfgEnableBlack.checked = defaultCfg.enable_black_fades ?? true;
  if (dom.cfgEnableWhite) dom.cfgEnableWhite.checked = defaultCfg.enable_white_fades ?? true;
  if (dom.cfgEnableVisual) dom.cfgEnableVisual.checked = defaultCfg.enable_visual_cuts ?? false;
  if (dom.cfgEnableSub) dom.cfgEnableSub.checked = defaultCfg.enable_subdivide ?? false;
  if (dom.cfgWorkers) dom.cfgWorkers.value = defaultCfg.workers ?? 8;
  if (dom.cfgTitleTemplate) dom.cfgTitleTemplate.value = defaultCfg.title_template || "Scene {n:02d}";
  if (dom.cfgCardDur) dom.cfgCardDur.value = defaultCfg.card_dur ?? 8.4;

  [
    dom.cfgMin,
    dom.cfgMax,
    dom.cfgTarget,
    dom.cfgTh,
    dom.cfgBlackDur,
    dom.cfgBlackPicTh,
    dom.cfgBlackPixTh,
    dom.cfgWhitePicTh,
    dom.cfgWhitePixTh,
    dom.cfgEnableBlack,
    dom.cfgEnableWhite,
    dom.cfgEnableVisual,
    dom.cfgEnableSub,
    dom.cfgWorkers,
    dom.cfgTitleTemplate,
    dom.cfgCardDur,
  ].forEach((el) => {
    el?.addEventListener("change", () => {
      syncStageUI();
      markPresetCustom();
      saveSettingsToLocalStorage();
    });
  });
  syncStageUI();

  document.getElementById("preset-select")?.addEventListener("change", (e) => {
    const p = e.target.value;
    if (p !== "custom") {
      applyPreset(p);
    }
  });

  dom.resumeBrowserBtn?.addEventListener("click", () => showView("browser"));
  document.getElementById("switch-video-btn")?.addEventListener("click", () => showView("picker"));

  document.getElementById("up-dir-btn")?.addEventListener("click", async () => {
    const data = await fetchFs(state.currentDir, true);
    if (data.ok) loadDirectory(data.dir);
  });

  document.getElementById("go-path-btn")?.addEventListener("click", async () => {
    const raw = dom.dirInput?.value.trim();
    if (!raw) return;
    const data = await resolvePath(raw);
    if (data.ok && data.kind === "file") {
      if (data.parent_dir) await loadDirectory(data.parent_dir);
      startScan(data.path, false, onScanComplete);
    } else if (data.ok && data.kind === "dir") {
      loadDirectory(data.path);
    }
  });

  dom.dirInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      document.getElementById("go-path-btn")?.click();
    }
  });

  document.getElementById("redetect-btn")?.addEventListener("click", async () => {
    const raw = dom.dirInput?.value.trim();
    if (raw) {
      const data = await resolvePath(raw);
      if (data.ok && data.kind === "file") {
        if (data.parent_dir) await loadDirectory(data.parent_dir);
        startScan(data.path, true, onScanComplete);
        return;
      }
    }
    if (state.currentVideoPath) {
      startScan(state.currentVideoPath, true, onScanComplete);
    }
  });
}
