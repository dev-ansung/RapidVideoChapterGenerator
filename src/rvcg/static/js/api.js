import { state, dom } from "./state.js";

export function setStatus(text, isError = false, revealPath = "") {
  if (dom.statusPill) {
    dom.statusPill.textContent = text;
    dom.statusPill.className = isError
      ? "badge badge-error badge-sm"
      : text
      ? "badge badge-neutral badge-sm"
      : "badge badge-ghost badge-sm hidden";
  }
  if (dom.revealFileBtn) {
    if (revealPath) {
      dom.revealFileBtn.dataset.revealPath = revealPath;
      dom.revealFileBtn.classList.remove("hidden");
      const tipText = `Open file location: ${revealPath}`;
      dom.revealFileBtn.dataset.tippyContent = tipText;
      if (dom.revealFileBtn._tippy) {
        dom.revealFileBtn._tippy.setContent(tipText);
      } else if (typeof window.tippy !== "undefined") {
        window.tippy(dom.revealFileBtn, {
          placement: "bottom",
          delay: [40, 0],
          maxWidth: 520,
          appendTo: () => document.body,
        });
      }
    } else {
      dom.revealFileBtn.dataset.revealPath = "";
      dom.revealFileBtn.classList.add("hidden");
    }
  }
}

export function initStatusRevealBtn() {
  if (!dom.revealFileBtn) return;
  dom.revealFileBtn.addEventListener("click", async () => {
    const target = dom.revealFileBtn.dataset.revealPath;
    if (!target) return;
    await fetch("/api/fs/reveal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: target }),
    });
  });
}

export async function fetchFs(dirPath, parent = false) {
  const q = new URLSearchParams();
  if (dirPath) q.set("dir", dirPath);
  if (parent) q.set("parent", "1");
  const res = await fetch(`/api/fs?${q.toString()}`);
  return res.json();
}

export async function resolvePath(pathStr) {
  const res = await fetch("/api/resolve-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: pathStr }),
  });
  return res.json();
}

export async function recalcChapters(rawChapters) {
  const res = await fetch("/api/chapters/recalc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chapters: rawChapters }),
  });
  return res.json();
}

export async function saveChapters(videoPath, chapters) {
  const res = await fetch("/api/chapters/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: videoPath, chapters }),
  });
  return res.json();
}

export async function exportChaptersText(format, chapters) {
  const res = await fetch("/api/chapters/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format, chapters }),
  });
  return res.json();
}

export async function exportSceneClip(videoPath, sceneObj, targetOut, includeIntro = true) {
  const res = await fetch("/api/chapters/export-scene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: videoPath,
      scene: sceneObj,
      output_path: targetOut.trim(),
      include_intro: Boolean(includeIntro),
    }),
  });
  return res.json();
}

export async function startScanJob(payload) {
  const res = await fetch("/api/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

