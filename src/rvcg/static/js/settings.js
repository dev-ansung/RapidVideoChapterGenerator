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

  if (setMin && dom.cfgMin) setMin.value = dom.cfgMin.value;
  if (setBlackDur && dom.cfgBlackDur) setBlackDur.value = dom.cfgBlackDur.value;
  if (setTh && dom.cfgTh) setTh.value = dom.cfgTh.value;
  if (setMax && dom.cfgMax) setMax.value = dom.cfgMax.value;
  if (setTarget && dom.cfgTarget) setTarget.value = dom.cfgTarget.value;
  syncThemePreference();
}

export function initSettingsAndExport() {
  try {
    if (dom.prefShowCutDot) {
      dom.prefShowCutDot.checked = localStorage.getItem("rvcg_show_cut_dot") !== "false";
    }
  } catch (_) {}
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

  setMin?.addEventListener("change", () => {
    if (dom.cfgMin) dom.cfgMin.value = setMin.value;
  });
  setBlackDur?.addEventListener("change", () => {
    if (dom.cfgBlackDur) dom.cfgBlackDur.value = setBlackDur.value;
  });
  setTh?.addEventListener("change", () => {
    if (dom.cfgTh) dom.cfgTh.value = setTh.value;
  });
  setMax?.addEventListener("change", () => {
    if (dom.cfgMax) dom.cfgMax.value = setMax.value;
  });
  setTarget?.addEventListener("change", () => {
    if (dom.cfgTarget) dom.cfgTarget.value = setTarget.value;
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
