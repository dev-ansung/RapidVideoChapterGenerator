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
  const setWorkers = document.getElementById("set-cfg-workers");
  if (setWorkers && dom.cfgWorkers) setWorkers.value = dom.cfgWorkers.value;
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

  const setWorkers = document.getElementById("set-cfg-workers");
  if (setWorkers && dom.cfgWorkers) {
    setWorkers.addEventListener("change", () => {
      dom.cfgWorkers.value = setWorkers.value;
      saveSettingsToLocalStorage();
    });
    dom.cfgWorkers.addEventListener("change", () => {
      setWorkers.value = dom.cfgWorkers.value;
      saveSettingsToLocalStorage();
    });
  }

  [
    dom.cfgMin,
    dom.cfgBlackDur,
    dom.cfgTh,
    dom.cfgMax,
    dom.cfgTarget,
    dom.cfgWorkers,
    dom.cfgEnableBlack,
    dom.cfgEnableVisual,
    dom.cfgEnableSub,
  ].forEach((el) => {
    el?.addEventListener("change", saveSettingsToLocalStorage);
  });

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
