import { state, dom } from "./state.js";
import { exportChaptersText, saveChapters, setStatus } from "./api.js";

export function syncCutDotPreference() {
  if (!dom.prefShowCutDot) return;
  document.body.classList.toggle("hide-cut-dots", !dom.prefShowCutDot.checked);
  try {
    localStorage.setItem("rvcg_show_cut_dot", dom.prefShowCutDot.checked ? "true" : "false");
  } catch (_) {}
}

export function initSettingsAndExport() {
  try {
    if (dom.prefShowCutDot) {
      dom.prefShowCutDot.checked = localStorage.getItem("rvcg_show_cut_dot") !== "false";
    }
  } catch (_) {}
  syncCutDotPreference();

  dom.prefShowCutDot?.addEventListener("change", syncCutDotPreference);

  document.querySelectorAll(".open-settings-btn").forEach((btn) => {
    btn.addEventListener("click", () => dom.settingsPopover?.showModal());
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
