import { state, dom } from "./state.js";
import { exportChaptersText, saveChapters, setStatus } from "./api.js";

export function syncCutDotPreference() {
  if (!dom.prefShowCutDot) return;
  document.body.classList.toggle("hide-cut-dots", !dom.prefShowCutDot.checked);
  try {
    localStorage.setItem("rvcg_show_cut_dot", dom.prefShowCutDot.checked ? "true" : "false");
  } catch (_) {}
}

export function syncThemePreference() {
  let saved = "black";
  try {
    saved = localStorage.getItem("rvcg_theme") || "black";
  } catch (_) {}
  document.documentElement.setAttribute("data-theme", saved);
  document.querySelectorAll(".theme-switcher-select, #pref-theme-select").forEach((el) => {
    el.value = saved;
  });
}

export function syncSettingsInputsFromConfig() {
  const setMin = document.getElementById("set-cfg-min");
  const setBlackDur = document.getElementById("set-cfg-black-dur");
  const setTh = document.getElementById("set-cfg-th");
  const setMax = document.getElementById("set-cfg-max");
  const setTarget = document.getElementById("set-cfg-target");
  const setWorkers = document.getElementById("set-cfg-workers");
  const setEnBlack = document.getElementById("set-cfg-enable-black");
  const setEnVisual = document.getElementById("set-cfg-enable-visual");
  const setEnSub = document.getElementById("set-cfg-enable-sub");

  if (setMin && dom.cfgMin) setMin.value = dom.cfgMin.value;
  if (setBlackDur && dom.cfgBlackDur) setBlackDur.value = dom.cfgBlackDur.value;
  if (setTh && dom.cfgTh) setTh.value = dom.cfgTh.value;
  if (setMax && dom.cfgMax) setMax.value = dom.cfgMax.value;
  if (setTarget && dom.cfgTarget) setTarget.value = dom.cfgTarget.value;
  if (setWorkers && dom.cfgWorkers) setWorkers.value = dom.cfgWorkers.value;
  if (setEnBlack && dom.cfgEnableBlack) setEnBlack.checked = dom.cfgEnableBlack.checked;
  if (setEnVisual && dom.cfgEnableVisual) setEnVisual.checked = dom.cfgEnableVisual.checked;
  if (setEnSub && dom.cfgEnableSub) setEnSub.checked = dom.cfgEnableSub.checked;
  syncThemePreference();
}

export function saveSettingsToLocalStorage() {
  try {
    if (dom.cfgMin) localStorage.setItem("rvcg_cfg_min", dom.cfgMin.value);
    if (dom.cfgBlackDur) localStorage.setItem("rvcg_cfg_black_dur", dom.cfgBlackDur.value);
    if (dom.cfgTh) localStorage.setItem("rvcg_cfg_th", dom.cfgTh.value);
    if (dom.cfgMax) localStorage.setItem("rvcg_cfg_max", dom.cfgMax.value);
    if (dom.cfgTarget) localStorage.setItem("rvcg_cfg_target", dom.cfgTarget.value);
    if (dom.cfgWorkers) localStorage.setItem("rvcg_cfg_workers", dom.cfgWorkers.value);
    if (dom.cfgEnableBlack) localStorage.setItem("rvcg_cfg_enable_black", dom.cfgEnableBlack.checked ? "true" : "false");
    if (dom.cfgEnableVisual) localStorage.setItem("rvcg_cfg_enable_visual", dom.cfgEnableVisual.checked ? "true" : "false");
    if (dom.cfgEnableSub) localStorage.setItem("rvcg_cfg_enable_sub", dom.cfgEnableSub.checked ? "true" : "false");
  } catch (_) {}
}

export function loadSettingsFromLocalStorage() {
  try {
    const minVal = localStorage.getItem("rvcg_cfg_min");
    if (minVal && dom.cfgMin) dom.cfgMin.value = minVal;

    const bdVal = localStorage.getItem("rvcg_cfg_black_dur");
    if (bdVal && dom.cfgBlackDur) dom.cfgBlackDur.value = bdVal;

    const thVal = localStorage.getItem("rvcg_cfg_th");
    if (thVal && dom.cfgTh) dom.cfgTh.value = thVal;

    const maxVal = localStorage.getItem("rvcg_cfg_max");
    if (maxVal && dom.cfgMax) dom.cfgMax.value = maxVal;

    const targetVal = localStorage.getItem("rvcg_cfg_target");
    if (targetVal && dom.cfgTarget) dom.cfgTarget.value = targetVal;

    const workersVal = localStorage.getItem("rvcg_cfg_workers");
    if (workersVal && dom.cfgWorkers) dom.cfgWorkers.value = workersVal;

    const ebVal = localStorage.getItem("rvcg_cfg_enable_black");
    if (ebVal !== null && dom.cfgEnableBlack) dom.cfgEnableBlack.checked = ebVal === "true";

    const evVal = localStorage.getItem("rvcg_cfg_enable_visual");
    if (evVal !== null && dom.cfgEnableVisual) dom.cfgEnableVisual.checked = evVal === "true";

    const esVal = localStorage.getItem("rvcg_cfg_enable_sub");
    if (esVal !== null && dom.cfgEnableSub) dom.cfgEnableSub.checked = esVal === "true";
  } catch (_) {}
}

export function initSettingsAndExport() {
  try {
    if (dom.prefShowCutDot) {
      dom.prefShowCutDot.checked = localStorage.getItem("rvcg_show_cut_dot") !== "false";
    }
  } catch (_) {}
  loadSettingsFromLocalStorage();
  syncCutDotPreference();
  syncThemePreference();

  dom.prefShowCutDot?.addEventListener("change", syncCutDotPreference);
  document.querySelectorAll(".theme-switcher-select, #pref-theme-select").forEach((el) => {
    el.addEventListener("change", (e) => {
      const val = e.target.value || "black";
      document.documentElement.setAttribute("data-theme", val);
      document.querySelectorAll(".theme-switcher-select, #pref-theme-select").forEach((other) => {
        other.value = val;
      });
      try {
        localStorage.setItem("rvcg_theme", val);
      } catch (_) {}
    });
  });

  const setMin = document.getElementById("set-cfg-min");
  const setBlackDur = document.getElementById("set-cfg-black-dur");
  const setTh = document.getElementById("set-cfg-th");
  const setMax = document.getElementById("set-cfg-max");
  const setTarget = document.getElementById("set-cfg-target");
  const setWorkers = document.getElementById("set-cfg-workers");
  const setEnBlack = document.getElementById("set-cfg-enable-black");
  const setEnVisual = document.getElementById("set-cfg-enable-visual");
  const setEnSub = document.getElementById("set-cfg-enable-sub");

  const wireTwoWay = (setEl, cfgEl, isCheckbox = false) => {
    if (!setEl || !cfgEl) return;
    setEl.addEventListener("change", () => {
      if (isCheckbox) cfgEl.checked = setEl.checked;
      else cfgEl.value = setEl.value;
      saveSettingsToLocalStorage();
    });
    cfgEl.addEventListener("change", () => {
      if (isCheckbox) setEl.checked = cfgEl.checked;
      else setEl.value = cfgEl.value;
      saveSettingsToLocalStorage();
    });
  };

  wireTwoWay(setMin, dom.cfgMin);
  wireTwoWay(setBlackDur, dom.cfgBlackDur);
  wireTwoWay(setTh, dom.cfgTh);
  wireTwoWay(setMax, dom.cfgMax);
  wireTwoWay(setTarget, dom.cfgTarget);
  wireTwoWay(setWorkers, dom.cfgWorkers);
  wireTwoWay(setEnBlack, dom.cfgEnableBlack, true);
  wireTwoWay(setEnVisual, dom.cfgEnableVisual, true);
  wireTwoWay(setEnSub, dom.cfgEnableSub, true);

  document.querySelectorAll(".open-settings-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      syncSettingsInputsFromConfig();
      dom.settingsPopover?.showModal();
    });
  });

  document.getElementById("close-settings")?.addEventListener("click", () => {
    dom.settingsPopover?.close();
  });

  document.getElementById("export-menu-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    dom.exportDropdown?.classList.toggle("hidden");
  });

  document.addEventListener("click", () => {
    dom.exportDropdown?.classList.add("hidden");
  });

  dom.exportDropdown?.querySelectorAll("button[data-fmt]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const fmt = btn.dataset.fmt;
      dom.exportDropdown?.classList.add("hidden");
      if (!state.cuts.length) return;
      const data = await exportChaptersText(fmt, state.cuts);
      if (data.ok) {
        if (dom.exportTitle) dom.exportTitle.textContent = `Export (${fmt.toUpperCase()})`;
        if (dom.exportTextarea) dom.exportTextarea.value = data.content;
        dom.exportPopover?.showModal();
      }
    });
  });

  document.getElementById("copy-export-btn")?.addEventListener("click", () => {
    if (dom.exportTextarea) navigator.clipboard.writeText(dom.exportTextarea.value);
  });

  document.getElementById("close-export")?.addEventListener("click", () => {
    dom.exportPopover?.close();
  });

  dom.saveChaptersBtn?.addEventListener("click", async () => {
    if (!state.currentVideoPath || !state.cuts.length) return;
    setStatus("Embedding...", false);
    const data = await saveChapters(state.currentVideoPath, state.cuts);
    if (data.ok) {
      setStatus("✓ Embedded", false);
    } else {
      setStatus("Embed failed: " + (data.error || ""), true);
    }
  });

  if (typeof window.tippy !== "undefined") {
    window.tippy(document.querySelectorAll("#picker-view [data-tippy-content]"), {
      placement: "top",
      delay: [60, 0],
      maxWidth: 320,
      appendTo: () => document.body,
    });
  }
}
