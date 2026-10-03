import { state, dom, fmtHms, fmtHmsMs, parseTimeInput, setCellSpriteFrame, cutDotColorClass } from "./state.js";
import { player, refreshSeekbarMarkers } from "./player.js";
import { exportSceneClip, setStatus, recalcChapters } from "./api.js";

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
        detail: c.detail || `Black fade @ ${fmtHmsMs(ts)}`,
        label: "Black Fade",
      });
    } else if (c.kind === "visual" && vOn && sc >= th) {
      out.push({
        timestamp: ts,
        kind: "visual",
        score: sc,
        detail: c.detail || `Visual cut @ ${fmtHmsMs(ts)} (score=${sc.toFixed(3)})`,
        label: `Visual ${sc.toFixed(2)}`,
      });
    }
  });

  state.cuts.forEach((ch) => {
    if (!out.some((x) => Math.abs(x.timestamp - ch.start_time) < 0.15)) {
      out.push({
        timestamp: ch.start_time,
        kind: ch.cut_kind || "start",
        score: 1.5,
        detail: ch.cut_detail || `Chapter #${ch.id} start @ ${fmtHmsMs(ch.start_time)}`,
        label: `Chapter #${ch.id}`,
      });
    }
  });

  const totalDur = getTotalDuration();
  if (totalDur > 0 && !out.some((x) => Math.abs(x.timestamp - totalDur) < 0.15)) {
    out.push({
      timestamp: Math.round(totalDur * 100) / 100,
      kind: "start",
      score: 1.5,
      detail: `Video end @ ${fmtHmsMs(totalDur)}`,
      label: "Video End",
    });
  }

  out.sort((a, b) => a.timestamp - b.timestamp);
  return out;
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
  if (!sceneObj) return;
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

export function getSlidingCandidateCuts(targetT) {
  const allCands = getActiveCandidateCuts();
  const prevPool = allCands.filter((c) => c.timestamp < targetT - 0.05);
  const nextPool = allCands.filter((c) => c.timestamp > targetT + 0.05);

  const prev3 = prevPool.slice(-3);
  const next3 = nextPool.slice(0, 3);

  return { prev: prev3, next: next3 };
}

export function renderCandidateCards(containerEl, cands, targetT, onSelect) {
  if (!containerEl) return;
  containerEl.innerHTML = "";

  if (!cands || !cands.length) {
    const emptyMsg = document.createElement("div");
    emptyMsg.className = "col-span-3 flex items-center justify-center h-28 text-xs text-base-content/40 italic";
    emptyMsg.textContent = "No nearby candidates detected";
    containerEl.appendChild(emptyMsg);
    return;
  }

  cands.forEach((cand) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "split-cand-card btn btn-outline btn-sm h-auto flex flex-col p-1 text-left justify-start items-stretch font-normal rounded-box border-base-content/20 hover:border-primary transition-all";
    btn.dataset.ts = cand.timestamp;
    btn.dataset.tippyContent = cand.detail || cand.label;

    const thumb = document.createElement("div");
    thumb.className = "relative aspect-video w-full rounded bg-base-300 overflow-hidden bg-no-repeat";
    setCellSpriteFrame(thumb, cand.timestamp);
    attachHoverPreviewVideo(thumb, () => cand.timestamp);

    const delta = cand.timestamp - targetT;
    const deltaBadge = document.createElement("span");
    deltaBadge.className = "absolute top-1 right-1 px-1 py-0.5 rounded bg-black/80 text-[10px] text-white font-mono pointer-events-none";
    deltaBadge.textContent = `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}s`;
    thumb.appendChild(deltaBadge);

    const meta = document.createElement("div");
    meta.className = "flex items-center justify-between gap-1.5 mt-1 px-0.5 w-full";

    const row = document.createElement("div");
    row.className = "flex items-center gap-1 min-w-0 shrink-0";
    const dot = document.createElement("span");
    dot.className = `cut-dot inline-block w-2 h-2 rounded-full shrink-0 ${cutDotColorClass(cand.kind || "start")}`;
    const tsSpan = document.createElement("span");
    tsSpan.className = "text-[11px] font-mono font-semibold shrink-0";
    tsSpan.textContent = fmtHms(cand.timestamp);
    row.appendChild(dot);
    row.appendChild(tsSpan);

    const lbl = document.createElement("span");
    lbl.className = "text-[10px] text-base-content/60 truncate max-w-[55px] shrink-0 text-right ml-auto";
    lbl.textContent = cand.label;

    meta.appendChild(row);
    meta.appendChild(lbl);

    btn.appendChild(thumb);
    btn.appendChild(meta);

    const isClose = Math.abs(cand.timestamp - targetT) < 0.15;
    if (isClose) {
      btn.classList.add("ring-2", "ring-primary");
    }

    btn.addEventListener("click", () => onSelect(cand.timestamp));
    containerEl.appendChild(btn);
  });

  if (typeof window.tippy !== "undefined") {
    window.tippy(containerEl.querySelectorAll(".split-cand-card"), {
      placement: "top",
      delay: [40, 0],
      maxWidth: 320,
      appendTo: () => dom.splitModalPopover || document.body,
    });
  }
}

export function updateSplitCandidates(targetT, updateInput = false) {
  const totalDur = getTotalDuration() || 36000;
  let t = Number(targetT);
  if (Number.isNaN(t)) t = 0;
  t = Math.max(0, Math.min(totalDur, Math.round(t * 1000) / 1000));

  if (updateInput && dom.splitTimeInput) {
    dom.splitTimeInput.value = fmtHmsMs(t);
  }
  if (dom.splitTargetBadge) {
    dom.splitTargetBadge.textContent = fmtHmsMs(t);
  }
  if (dom.splitThumb) {
    setCellSpriteFrame(dom.splitThumb, t);
  }

  const { prev, next } = getSlidingCandidateCuts(t);
  renderCandidateCards(dom.splitPrevCands, prev, t, (ts) => updateSplitCandidates(ts, true));
  renderCandidateCards(dom.splitNextCands, next, t, (ts) => updateSplitCandidates(ts, true));

  if (dom.splitSegmentInfo) {
    const chap = getActiveChapterAt(t);
    const leftDur = Math.max(0, t - chap.start_time);
    const rightDur = Math.max(0, chap.end_time - t);
    dom.splitSegmentInfo.textContent = `Scene #${chap.id}: [${fmtHms(chap.start_time)} → ${fmtHms(chap.end_time)}] ➔ ${fmtHms(leftDur)} + ${fmtHms(rightDur)}`;
  }
}

export function jumpSemanticCut(kind, direction) {
  const currentT = parseTimeInput(dom.splitTimeInput?.value) || ((player && player.currentTime()) || 0);
  const allCands = getActiveCandidateCuts();

  const matching = allCands.filter((c) => {
    if (kind === "black") return c.kind === "black";
    if (kind === "visual") return c.kind === "visual";
    if (kind === "chapter") return c.kind === "start" || c.kind === "subdivide" || c.kind === "manual";
    return true;
  });

  if (direction === "prev") {
    const prevMatches = matching.filter((c) => c.timestamp < currentT - 0.05);
    if (prevMatches.length) {
      const target = prevMatches[prevMatches.length - 1];
      updateSplitCandidates(target.timestamp, true);
    }
  } else if (direction === "next") {
    const nextMatches = matching.filter((c) => c.timestamp > currentT + 0.05);
    if (nextMatches.length) {
      const target = nextMatches[0];
      updateSplitCandidates(target.timestamp, true);
    }
  }
}

export function openSplitModal() {
  if (!state.currentVideoPath || !state.cuts.length) return;
  const playheadT = Math.round(((player && player.currentTime()) || 0) * 1000) / 1000;
  updateSplitCandidates(playheadT, true);
  dom.splitModalPopover?.showModal();
}

export async function confirmSplit(onChaptersChanged) {
  const t = parseTimeInput(dom.splitTimeInput?.value);
  if (Number.isNaN(t)) return;
  const idx = state.cuts.findIndex((c) => t > c.start_time + 0.1 && t < c.end_time - 0.1);
  if (idx === -1) {
    window.alert("Split position must be inside an existing scene (at least 0.1s from boundary).");
    return;
  }

  const next = state.cuts.map((c) => ({
    start_time: c.start_time,
    end_time: c.end_time,
    title: c.title,
    cut_kind: c.cut_kind,
    cut_detail: c.cut_detail,
  }));
  const origEnd = next[idx].end_time;
  next[idx].end_time = t;
  next.splice(idx + 1, 0, {
    start_time: t,
    end_time: origEnd,
    title: `Scene ${String(idx + 2).padStart(2, "0")}`,
    cut_kind: "manual",
    cut_detail: `Manual split @ ${fmtHmsMs(t)}`,
  });

  const res = await recalcChapters(next);
  if (res.ok) {
    state.cuts = res.chapters;
    refreshSeekbarMarkers();
    if (onChaptersChanged) onChaptersChanged();
    dom.splitModalPopover?.close();
  }
}

export function initSplitModal(onChaptersChanged) {
  if (dom.splitThumb) {
    attachHoverPreviewVideo(dom.splitThumb, () => parseTimeInput(dom.splitTimeInput?.value));
  }

  dom.splitTimeInput?.addEventListener("change", () => {
    const t = parseTimeInput(dom.splitTimeInput?.value);
    if (!Number.isNaN(t)) updateSplitCandidates(t, false);
  });

  document.querySelectorAll("[data-nudge-split]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const delta = Number(btn.dataset.nudgeSplit || 0);
      const cur = parseTimeInput(dom.splitTimeInput?.value) || 0;
      updateSplitCandidates(cur + delta, true);
    });
  });

  document.querySelectorAll("[data-jump-kind]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.jumpKind;
      const dir = btn.dataset.jumpDir;
      jumpSemanticCut(kind, dir);
    });
  });

  dom.splitUsePlayheadBtn?.addEventListener("click", () => {
    const playheadT = (player && player.currentTime()) || 0;
    updateSplitCandidates(playheadT, true);
  });

  dom.splitPreviewBtn?.addEventListener("click", () => {
    const t = parseTimeInput(dom.splitTimeInput?.value);
    if (!Number.isNaN(t) && player) {
      player.currentTime(Math.max(0, t));
      player.play().catch(() => {});
    }
  });

  dom.confirmSplitBtn?.addEventListener("click", () => {
    confirmSplit(onChaptersChanged);
  });

  dom.cancelSplitBtn?.addEventListener("click", () => {
    dom.splitModalPopover?.close();
  });

  dom.closeSplitModal?.addEventListener("click", () => {
    dom.splitModalPopover?.close();
  });

  document.getElementById("split-here-btn")?.addEventListener("click", () => {
    openSplitModal();
  });

  dom.exportSceneBtn?.addEventListener("click", async () => {
    if (!state.currentVideoPath || !state.cuts.length) return;
    const playheadT = (player && player.currentTime()) || 0;
    const chap = getActiveChapterAt(playheadT);
    await promptAndExportScene(chap, "cut");
  });
}
