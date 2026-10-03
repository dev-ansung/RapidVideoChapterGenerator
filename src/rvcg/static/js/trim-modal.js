import { state, dom, fmtHms, fmtHmsMs, parseTimeInput, setCellSpriteFrame, cutDotColorClass } from "./state.js";
import { player } from "./player.js";
import { exportSceneClip, setStatus } from "./api.js";

export function getTotalDuration() {
  return (player && player.duration()) || (state.cuts.length ? state.cuts[state.cuts.length - 1].end_time : 0);
}

export function getActiveChapterAt(t) {
  if (!state.cuts.length) {
    return {
      id: "01",
      scene_number: 1,
      start_time: 0,
      end_time: Math.max(1, getTotalDuration()),
      title: "Scene 01",
      card_dur: 8.4,
    };
  }
  let idx = state.cuts.findIndex((c) => t >= c.start_time && t < c.end_time);
  if (idx === -1) idx = state.currentIndex >= 0 && state.currentIndex < state.cuts.length ? state.currentIndex : 0;
  return state.cuts[idx];
}

export function getActiveCandidateCuts() {
  const bOn = dom.cfgEnableBlack?.checked;
  const vOn = dom.cfgEnableVisual?.checked;
  const th = Number(dom.cfgTh?.value || 0.38);
  const out = [];

  state.rawCandidates.forEach((c) => {
    const ts = Number(c.timestamp || 0);
    const sc = Number(c.score || 0);
    if (c.kind === "black" && bOn) {
      out.push({
        timestamp: ts,
        kind: "black",
        score: 2.0,
        detail: c.detail || `Black fade @ ${fmtHms(ts)}`,
        label: "Black Fade",
      });
    } else if (c.kind === "visual" && vOn && sc >= th) {
      out.push({
        timestamp: ts,
        kind: "visual",
        score: sc,
        detail: c.detail || `Visual cut @ ${fmtHms(ts)} (score=${sc.toFixed(3)})`,
        label: `Visual ${sc.toFixed(2)}`,
      });
    }
  });

  state.cuts.forEach((ch) => {
    if (!out.some((x) => Math.abs(x.timestamp - ch.start_time) < 0.4)) {
      out.push({
        timestamp: ch.start_time,
        kind: ch.cut_kind || "start",
        score: 1.5,
        detail: ch.cut_detail || `Chapter #${ch.id} start @ ${fmtHms(ch.start_time)}`,
        label: `Chapter #${ch.id}`,
      });
    }
  });

  const totalDur = getTotalDuration();
  if (totalDur > 0 && !out.some((x) => Math.abs(x.timestamp - totalDur) < 0.4)) {
    out.push({
      timestamp: Math.round(totalDur * 100) / 100,
      kind: "start",
      score: 1.5,
      detail: `Video end @ ${fmtHms(totalDur)}`,
      label: "Video End",
    });
  }

  out.sort((a, b) => a.timestamp - b.timestamp);
  return out;
}

export function getNearestSceneAt(playheadT) {
  const chap = getActiveChapterAt(playheadT);
  const cands = getActiveCandidateCuts();
  const before = cands.filter((c) => c.timestamp <= playheadT - 0.3);
  const startT = before.length ? before[before.length - 1].timestamp : chap.start_time;
  const after = cands.filter((c) => c.timestamp >= Math.max(playheadT + 0.3, startT + 1.0));
  const endT = after.length ? after[0].timestamp : Math.max(startT + 1.0, chap.end_time);
  return {
    id: chap.id || "01",
    scene_number: chap.scene_number || 1,
    start_time: Math.round(startT * 100) / 100,
    end_time: Math.round(endT * 100) / 100,
    title: chap.title || "Scene 01",
    card_dur: chap.card_dur || 8.4,
  };
}

export function buildDefaultExportPath(sceneObj, prefix = "cut") {
  const slug = fmtHms(sceneObj.start_time).replace(/:/g, "-");
  const baseStem = state.currentVideoPath.replace(/\.[^/.]+$/, "");
  return `${baseStem}_cuts/${prefix}_${sceneObj.id || "01"}_${slug}.mp4`;
}

export async function executeSceneExport(sceneObj, targetOut, btnEl, includeIntro = true) {
  if (!state.currentVideoPath || !targetOut || !targetOut.trim()) return false;
  const origText = btnEl ? btnEl.textContent : "";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "Exporting...";
  }
  setStatus(`Exporting ${fmtHms(sceneObj.start_time)}–${fmtHms(sceneObj.end_time)}...`, false);
  try {
    const data = await exportSceneClip(state.currentVideoPath, sceneObj, targetOut, includeIntro);
    if (data.ok) {
      setStatus("", false, data.path);
      return true;
    }
    setStatus(`Export failed: ${data.error || "error"}`, true);
    return false;
  } catch (_) {
    setStatus("Export failed", true);
    return false;
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = origText;
    }
  }
}

export async function promptAndExportScene(sceneObj, prefix = "cut") {
  const defaultOut = buildDefaultExportPath(sceneObj, prefix);
  const targetOut = window.prompt("Save exported scene to:", defaultOut);
  if (!targetOut || !targetOut.trim()) return;
  await executeSceneExport(sceneObj, targetOut, dom.exportSceneBtn, true);
}

export function attachHoverPreviewVideo(thumbEl, getTimeFn) {
  let vEl = null;
  thumbEl.addEventListener("mouseenter", () => {
    if (vEl || !state.videoSrc) return;
    const t = Math.max(0, Number(getTimeFn() || 0));
    vEl = document.createElement("video");
    vEl.src = state.videoSrc;
    vEl.muted = true;
    vEl.playsInline = true;
    vEl.preload = "auto";
    vEl.className = "absolute inset-0 w-full h-full object-cover z-0 pointer-events-none";
    vEl.addEventListener("loadedmetadata", () => {
      if (!vEl) return;
      vEl.currentTime = t;
    });
    thumbEl.appendChild(vEl);
  });
  thumbEl.addEventListener("mouseleave", () => {
    if (!vEl) return;
    vEl.pause();
    vEl.removeAttribute("src");
    vEl.load();
    vEl.remove();
    vEl = null;
  });
}

export function pickTopCandidates(pool, mustIncludeTimes, playheadT, maxCount = 6) {
  const chosen = [];
  const addUnique = (cand) => {
    if (!cand) return;
    if (chosen.some((x) => Math.abs(x.timestamp - cand.timestamp) < 0.35)) return;
    chosen.push(cand);
  };
  mustIncludeTimes.forEach((t) => {
    const match = pool.find((c) => Math.abs(c.timestamp - t) < 0.35);
    if (match) addUnique(match);
  });
  const ranked = [...pool].sort((a, b) => {
    const distA = Math.abs(a.timestamp - playheadT);
    const distB = Math.abs(b.timestamp - playheadT);
    const rankA = distA / (1 + a.score * 1.5);
    const rankB = distB / (1 + b.score * 1.5);
    return rankA - rankB;
  });
  for (const c of ranked) {
    if (chosen.length >= maxCount) break;
    addUnique(c);
  }
  chosen.sort((a, b) => a.timestamp - b.timestamp);
  return chosen;
}

export function syncManualTrimUI(updateInputs = false) {
  const totalDur = getTotalDuration() || 36000;
  let s = parseTimeInput(dom.manualStartInput?.value);
  let e = parseTimeInput(dom.manualEndInput?.value);
  if (Number.isNaN(s)) s = 0;
  if (Number.isNaN(e)) e = Math.max(s + 1, totalDur);
  s = Math.max(0, Math.min(totalDur - 0.5, s));
  e = Math.max(s + 0.5, Math.min(totalDur, e));

  if (updateInputs) {
    if (dom.manualStartInput) dom.manualStartInput.value = fmtHmsMs(s);
    if (dom.manualEndInput) dom.manualEndInput.value = fmtHmsMs(e);
  }

  if (dom.manualStartThumb) setCellSpriteFrame(dom.manualStartThumb, s);
  if (dom.manualEndThumb) setCellSpriteFrame(dom.manualEndThumb, Math.max(0, e - 0.2));

  dom.manualStartCands?.querySelectorAll(".trim-cand-card").forEach((el) => {
    const isSel = Math.abs(Number(el.dataset.ts) - s) < 0.25;
    el.classList.toggle("ring-2", isSel);
    el.classList.toggle("ring-primary", isSel);
  });
  dom.manualEndCands?.querySelectorAll(".trim-cand-card").forEach((el) => {
    const isSel = Math.abs(Number(el.dataset.ts) - e) < 0.25;
    el.classList.toggle("ring-2", isSel);
    el.classList.toggle("ring-primary", isSel);
  });

  const dur = Math.max(0.5, e - s);
  if (dom.manualDurLabel) {
    dom.manualDurLabel.textContent = `Trim Range: ${fmtHmsMs(s)} – ${fmtHmsMs(e)} (${dur.toFixed(1)}s)`;
  }

  if (!state.manualPathTouched && dom.manualPathInput) {
    const chap = getActiveChapterAt(state.manualPlayheadRef);
    dom.manualPathInput.value = buildDefaultExportPath(
      { id: chap.id || "01", start_time: s },
      "trim"
    );
  }
}

export function syncManualIntroPreference() {
  if (!dom.manualIncludeIntro) return;
  const on = Boolean(dom.manualIncludeIntro.checked);
  if (dom.manualTitleInput) dom.manualTitleInput.disabled = !on;
  if (dom.manualTitleField) dom.manualTitleField.classList.toggle("opacity-50", !on);
  try {
    localStorage.setItem("rvcg_manual_include_intro", on ? "true" : "false");
  } catch (_) {}
}

export function renderCandidateCards(containerEl, cands, playheadT, onSelect) {
  if (!containerEl) return;
  containerEl.innerHTML = "";
  cands.forEach((cand) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "trim-cand-card btn btn-outline btn-sm h-auto flex flex-col p-1 text-left justify-start items-stretch font-normal rounded-box border-base-content/20 hover:border-primary transition-all";
    btn.dataset.ts = cand.timestamp;
    btn.dataset.tippyContent = cand.detail || cand.label;

    const thumb = document.createElement("div");
    thumb.className = "relative aspect-video w-full rounded bg-base-300 overflow-hidden bg-no-repeat";
    setCellSpriteFrame(thumb, cand.timestamp);
    attachHoverPreviewVideo(thumb, () => cand.timestamp);

    const delta = cand.timestamp - playheadT;
    const deltaBadge = document.createElement("span");
    deltaBadge.className = "absolute top-1 right-1 px-1 py-0.5 rounded bg-black/80 text-[10px] text-white font-mono pointer-events-none";
    deltaBadge.textContent = `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}s`;
    thumb.appendChild(deltaBadge);

    const meta = document.createElement("div");
    meta.className = "flex items-center justify-between mt-1 px-0.5";

    const row = document.createElement("div");
    row.className = "flex items-center gap-1.5";
    const dot = document.createElement("span");
    dot.className = `cut-dot inline-block w-2 h-2 rounded-full shrink-0 ${cutDotColorClass(cand.kind || "start")}`;
    const tsSpan = document.createElement("span");
    tsSpan.className = "text-xs font-mono font-semibold";
    tsSpan.textContent = fmtHms(cand.timestamp);
    row.appendChild(dot);
    row.appendChild(tsSpan);

    const lbl = document.createElement("span");
    lbl.className = "text-[10px] text-base-content/60 truncate max-w-[70px]";
    lbl.textContent = cand.label;

    meta.appendChild(row);
    meta.appendChild(lbl);

    btn.appendChild(thumb);
    btn.appendChild(meta);
    btn.addEventListener("click", () => onSelect(cand.timestamp));
    containerEl.appendChild(btn);
  });

  if (typeof window.tippy !== "undefined") {
    window.tippy(containerEl.querySelectorAll(".trim-cand-card"), {
      placement: "top",
      delay: [40, 0],
      maxWidth: 340,
      appendTo: () => dom.manualExportPopover,
    });
  }
}

export function openManualExportModal() {
  if (!state.currentVideoPath || !state.cuts.length) return;
  const playheadT = Math.round(((player && player.currentTime()) || 0) * 100) / 100;
  state.manualPlayheadRef = playheadT;
  state.manualPathTouched = false;

  const chap = getActiveChapterAt(playheadT);
  const nearest = getNearestSceneAt(playheadT);
  const allCands = getActiveCandidateCuts();

  const beforePool = allCands.filter((c) => c.timestamp <= playheadT);
  if (!beforePool.some((c) => Math.abs(c.timestamp - playheadT) < 0.35)) {
    beforePool.push({
      timestamp: playheadT,
      kind: "manual",
      score: 1.8,
      detail: `Current playhead @ ${fmtHmsMs(playheadT)}`,
      label: "Playhead",
    });
  }
  const startCands = pickTopCandidates(
    beforePool,
    [nearest.start_time, chap.start_time, playheadT],
    playheadT,
    6
  );

  const afterPool = allCands.filter((c) => c.timestamp >= playheadT);
  if (!afterPool.some((c) => Math.abs(c.timestamp - playheadT) < 0.35) && playheadT > nearest.start_time + 0.5) {
    afterPool.push({
      timestamp: playheadT,
      kind: "manual",
      score: 1.8,
      detail: `Current playhead @ ${fmtHmsMs(playheadT)}`,
      label: "Playhead",
    });
  }
  const endCands = pickTopCandidates(
    afterPool,
    [nearest.end_time, chap.end_time],
    playheadT,
    6
  );

  if (dom.manualPlayheadLabel) dom.manualPlayheadLabel.textContent = `Playhead: ${fmtHmsMs(playheadT)}`;
  if (dom.manualStartInput) dom.manualStartInput.value = fmtHmsMs(nearest.start_time);
  if (dom.manualEndInput) dom.manualEndInput.value = fmtHmsMs(nearest.end_time);
  if (dom.manualTitleInput) dom.manualTitleInput.value = chap.title || "Scene 01";

  renderCandidateCards(dom.manualStartCands, startCands, playheadT, (ts) => {
    if (dom.manualStartInput) dom.manualStartInput.value = fmtHmsMs(ts);
    syncManualTrimUI(true);
  });
  renderCandidateCards(dom.manualEndCands, endCands, playheadT, (ts) => {
    if (dom.manualEndInput) dom.manualEndInput.value = fmtHmsMs(ts);
    syncManualTrimUI(true);
  });

  syncManualIntroPreference();
  syncManualTrimUI(true);
  dom.manualExportPopover?.showModal();
}

export function initTrimModal() {
  try {
    if (dom.manualIncludeIntro) {
      dom.manualIncludeIntro.checked = localStorage.getItem("rvcg_manual_include_intro") !== "false";
    }
  } catch (_) {}
  syncManualIntroPreference();
  dom.manualIncludeIntro?.addEventListener("change", syncManualIntroPreference);

  if (dom.manualStartThumb) attachHoverPreviewVideo(dom.manualStartThumb, () => parseTimeInput(dom.manualStartInput?.value));
  if (dom.manualEndThumb) attachHoverPreviewVideo(dom.manualEndThumb, () => parseTimeInput(dom.manualEndInput?.value));

  dom.manualStartInput?.addEventListener("change", () => syncManualTrimUI(true));
  dom.manualEndInput?.addEventListener("change", () => syncManualTrimUI(true));
  dom.manualPathInput?.addEventListener("input", () => {
    state.manualPathTouched = true;
  });

  document.querySelectorAll("[data-nudge-start]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const delta = Number(btn.dataset.nudgeStart || 0);
      const cur = parseTimeInput(dom.manualStartInput?.value) || 0;
      if (dom.manualStartInput) dom.manualStartInput.value = fmtHmsMs(Math.max(0, cur + delta));
      syncManualTrimUI(true);
    });
  });

  document.querySelectorAll("[data-nudge-end]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const delta = Number(btn.dataset.nudgeEnd || 0);
      const cur = parseTimeInput(dom.manualEndInput?.value) || 1;
      if (dom.manualEndInput) dom.manualEndInput.value = fmtHmsMs(Math.max(0.5, cur + delta));
      syncManualTrimUI(true);
    });
  });

  document.getElementById("manual-start-playhead-btn")?.addEventListener("click", () => {
    if (dom.manualStartInput) dom.manualStartInput.value = fmtHmsMs((player && player.currentTime()) || 0);
    syncManualTrimUI(true);
  });

  document.getElementById("manual-end-playhead-btn")?.addEventListener("click", () => {
    if (dom.manualEndInput) dom.manualEndInput.value = fmtHmsMs((player && player.currentTime()) || 1);
    syncManualTrimUI(true);
  });

  document.getElementById("manual-preview-btn")?.addEventListener("click", () => {
    const s = parseTimeInput(dom.manualStartInput?.value);
    if (!Number.isNaN(s) && player) {
      player.currentTime(Math.max(0, s));
      player.play().catch(() => {});
    }
  });

  document.getElementById("run-manual-export-btn")?.addEventListener("click", async () => {
    const s = parseTimeInput(dom.manualStartInput?.value);
    const e = parseTimeInput(dom.manualEndInput?.value);
    if (Number.isNaN(s) || Number.isNaN(e) || e <= s) return;
    const chap = getActiveChapterAt(state.manualPlayheadRef);
    const sceneObj = {
      id: chap.id || "01",
      scene_number: chap.scene_number || 1,
      start_time: Math.round(s * 100) / 100,
      end_time: Math.round(e * 100) / 100,
      title: dom.manualTitleInput?.value.trim() || chap.title || "Scene 01",
      card_dur: chap.card_dur || 8.4,
    };
    const ok = await executeSceneExport(
      sceneObj,
      dom.manualPathInput?.value.trim() || buildDefaultExportPath(sceneObj, "trim"),
      document.getElementById("run-manual-export-btn"),
      dom.manualIncludeIntro?.checked
    );
    if (ok) dom.manualExportPopover?.close();
  });

  document.getElementById("close-manual-export")?.addEventListener("click", () => {
    dom.manualExportPopover?.close();
  });

  dom.exportSceneBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    dom.exportSceneDropdown?.classList.toggle("hidden");
  });

  dom.exportSceneDropdown?.querySelectorAll("button[data-export-mode]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      dom.exportSceneDropdown?.classList.add("hidden");
      if (!state.currentVideoPath || !state.cuts.length) return;
      const mode = btn.dataset.exportMode;
      const playheadT = (player && player.currentTime()) || 0;
      if (mode === "chapter") {
        const chap = getActiveChapterAt(playheadT);
        await promptAndExportScene(chap, "cut");
      } else if (mode === "nearest") {
        const nearest = getNearestSceneAt(playheadT);
        await promptAndExportScene(nearest, "scene");
      } else if (mode === "manual") {
        openManualExportModal();
      }
    });
  });

  document.addEventListener("click", () => {
    dom.exportSceneDropdown?.classList.add("hidden");
  });
}
