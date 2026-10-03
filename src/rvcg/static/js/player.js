import { state, dom, setCellSpriteFrame, fmtHmsMs } from "./state.js";
import { recalcChapters, exportSceneClip, setStatus } from "./api.js";

export let player = null;
let hudTimeout = null;

export function showPlayerHud(text) {
  if (!dom.playerHudToast) return;
  dom.playerHudToast.textContent = text;
  dom.playerHudToast.classList.remove("opacity-0");
  dom.playerHudToast.classList.add("opacity-100");
  if (hudTimeout) clearTimeout(hudTimeout);
  hudTimeout = setTimeout(() => {
    if (dom.playerHudToast) {
      dom.playerHudToast.classList.remove("opacity-100");
      dom.playerHudToast.classList.add("opacity-0");
    }
  }, 1600);
}

export function isInPip() {
  if (!player) return false;
  const v = (player.el && player.el().querySelector("video")) || document.querySelector("#vjs-player video");
  return Boolean(
    document.pictureInPictureElement ||
    (typeof player.isInPictureInPicture === "function" && player.isInPictureInPicture()) ||
    (v && v.webkitPresentationMode === "picture-in-picture")
  );
}

export function applyPlayerBounds() {
  const maxW = Math.max(260, window.innerWidth - 20);
  if (state.winState.x === null || state.winState.y === null) {
    state.winState.w = Math.min(720, maxW);
    const initH = state.winState.w * (9 / 16) + 38;
    state.winState.x = Math.max(10, (window.innerWidth - state.winState.w) / 2);
    state.winState.y = Math.max(10, (window.innerHeight - initH) / 2);
  }
  state.winState.w = Math.max(260, Math.min(maxW, state.winState.w));
  const h = state.winState.w * (9 / 16) + 38;
  state.winState.x = Math.max(6, Math.min(window.innerWidth - state.winState.w - 6, state.winState.x));
  state.winState.y = Math.max(6, Math.min(window.innerHeight - h - 6, state.winState.y));
  if (dom.playerShell) {
    dom.playerShell.style.left = `${Math.round(state.winState.x)}px`;
    dom.playerShell.style.top = `${Math.round(state.winState.y)}px`;
    dom.playerShell.style.width = `${Math.round(state.winState.w)}px`;
  }
}

export function showPlayer(visible) {
  if (!visible) {
    if (!isInPip() && player) player.pause();
    dom.playerShell?.classList.add("hidden");
    return;
  }
  dom.playerShell?.classList.remove("hidden");
  applyPlayerBounds();
}

export function refreshSeekbarMarkers() {
  if (!player || !player.controlBar?.progressControl?.seekBar) return;
  const seekBar = player.controlBar.progressControl.seekBar;
  seekBar.el().querySelectorAll(".vjs-chapter-marker").forEach((m) => m.remove());
  const totalDur = player.duration() || (state.cuts.length ? state.cuts[state.cuts.length - 1].end_time : 0);
  if (totalDur > 0) {
    state.cuts.slice(1).forEach((seg) => {
      const marker = document.createElement("div");
      marker.className = "vjs-chapter-marker absolute top-0 bottom-0 w-0.5 bg-white/70 pointer-events-none z-10";
      marker.style.left = `${(seg.start_time / totalDur) * 100}%`;
      seekBar.el().appendChild(marker);
    });
  }
}

export function openAt(index, seekTime, onChapterActivated) {
  if (index < 0 || index >= state.cuts.length) return;
  const item = state.cuts[index];
  state.currentIndex = index;

  if (dom.nowBadge) dom.nowBadge.textContent = "#" + item.id;
  if (dom.nowTitle) dom.nowTitle.textContent = item.title;
  if (dom.nowRange) dom.nowRange.textContent = `${item.source_range} (${item.duration_str})`;
  if (onChapterActivated) onChapterActivated(index);

  if (!isInPip()) {
    showPlayer(true);
  }

  if (state.sourceLoaded) {
    player.currentTime(seekTime);
    player.play().catch(() => {});
  } else {
    state.sourceLoaded = true;
    player.src({ type: "video/mp4", src: state.videoSrc });
    player.one("loadedmetadata", () => {
      state.subtitles.forEach((sub) => {
        const blob = new Blob([sub.vtt], { type: "text/vtt;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const trackEl = player.addRemoteTextTrack(
          {
            kind: "subtitles",
            label: sub.label,
            srclang: sub.srclang,
            src: url,
            default: sub.default,
          },
          false
        );
        if (sub.default && trackEl && trackEl.track) {
          trackEl.track.mode = "showing";
        }
      });
      refreshSeekbarMarkers();
      player.currentTime(seekTime);
      player.play().catch(() => {});
    });
  }
}

export function seekCut(direction) {
  if (!player) return;
  const currTime = player.currentTime();
  const allCuts = [];

  (state.cuts || []).forEach((c) => {
    if (c.start_time > 0.05) {
      allCuts.push({
        timestamp: c.start_time,
        label: `Chapter #${c.id || ""}: ${c.title || ""}`.trim(),
      });
    }
  });

  (state.rawCandidates || []).forEach((rc) => {
    allCuts.push({
      timestamp: rc.timestamp,
      label: rc.detail || `${rc.kind || "cut"} transition @ ${fmtHmsMs(rc.timestamp)}`,
    });
  });

  allCuts.sort((a, b) => a.timestamp - b.timestamp);
  const deduped = [];
  for (const cut of allCuts) {
    if (!deduped.some((d) => Math.abs(d.timestamp - cut.timestamp) < 0.15)) {
      deduped.push(cut);
    }
  }

  if (!deduped.length) {
    showPlayerHud("No cut candidates recorded");
    return;
  }

  if (direction === "next") {
    const target = deduped.find((c) => c.timestamp > currTime + 0.15);
    if (target) {
      player.currentTime(target.timestamp);
      showPlayerHud(`🎯 ${target.label} (${fmtHmsMs(target.timestamp)})`);
    } else {
      showPlayerHud("No cut found forward");
    }
  } else {
    const rev = [...deduped].reverse();
    const target = rev.find((c) => c.timestamp < currTime - 0.15);
    if (target) {
      player.currentTime(target.timestamp);
      showPlayerHud(`🎯 ${target.label} (${fmtHmsMs(target.timestamp)})`);
    } else {
      showPlayerHud("No cut found backward");
    }
  }
}

async function splitCurrentScene(onChaptersChanged) {
  if (!player || !state.cuts.length) return;
  const currTime = player.currentTime();
  const activeIdx = state.cuts.findIndex((c) => currTime >= c.start_time && currTime < c.end_time);
  if (activeIdx === -1) {
    showPlayerHud("Playhead outside chapter range");
    return;
  }
  const curChapter = state.cuts[activeIdx];
  if (currTime <= curChapter.start_time + 0.1 || currTime >= curChapter.end_time - 0.1) {
    showPlayerHud("Cannot split at chapter boundaries");
    return;
  }

  const rawTuples = [];
  state.cuts.forEach((c, idx) => {
    if (idx === activeIdx) {
      rawTuples.push({
        start_time: c.start_time,
        end_time: currTime,
        title: c.title,
        kind: c.cut_kind || c.kind || "start",
      });
      rawTuples.push({
        start_time: currTime,
        end_time: c.end_time,
        title: `${c.title} (Part 2)`,
        kind: "manual",
      });
    } else {
      rawTuples.push({
        start_time: c.start_time,
        end_time: c.end_time,
        title: c.title,
        kind: c.cut_kind || c.kind || "start",
      });
    }
  });

  const res = await recalcChapters(rawTuples);
  if (res.ok && res.chapters) {
    state.cuts = res.chapters;
    refreshSeekbarMarkers();
    if (onChaptersChanged) onChaptersChanged();
    showPlayerHud(`✂ Split at ${fmtHmsMs(currTime)}`);
    setStatus("Unsaved edits", false);
  }
}

async function exportActiveScene() {
  if (!player || !state.cuts.length || !state.currentVideoPath) return;
  const currTime = player.currentTime();
  const activeIdx = state.cuts.findIndex((c) => currTime >= c.start_time && currTime < c.end_time);
  const targetIdx = activeIdx !== -1 ? activeIdx : (state.currentIndex >= 0 ? state.currentIndex : 0);
  const scene = state.cuts[targetIdx];
  const videoStem = state.currentVideoPath ? state.currentVideoPath.split("/").pop().replace(/\.[^/.]+$/, "") : "video";
  const sceneId = String(scene.id_str || scene.id || scene.scene_number || (targetIdx + 1)).padStart(2, "0");
  const timeSlug = fmtHms(scene.start_time).replace(/:/g, "-");
  const defaultOut = `${videoStem}_scene_${sceneId}_${timeSlug}.mp4`;
  const outPath = window.prompt(`Export Scene #${sceneId} ("${scene.title || `Scene ${sceneId}`}") to path:`, defaultOut);
  if (!outPath) return;

  showPlayerHud(`Exporting Scene #${sceneId}...`);
  try {
    const res = await exportSceneClip(state.currentVideoPath, scene, outPath, true);
    if (res.ok) {
      showPlayerHud(`✓ Exported: ${res.filename || outPath}`);
      setStatus(`Exported clip: ${res.filename || outPath}`, false, res.path);
    } else {
      showPlayerHud(`Export failed: ${res.error}`);
      setStatus(`Export failed: ${res.error}`, true);
    }
  } catch (err) {
    showPlayerHud(`Export error: ${err.message}`);
    setStatus(`Export error: ${err.message}`, true);
  }
}

export function initPlayer(onTimeUpdateChapter, onChaptersChanged) {
  player = window.videojs("vjs-player", {
    controls: true,
    autoplay: false,
    preload: "metadata",
    fluid: false,
    playbackRates: [0.5, 1, 1.25, 1.5, 2],
    controlBar: {
      SkipButtons: { forward: 10, backward: 10 },
    },
  });

  player.ready(() => {
    const progressControl = player.controlBar.progressControl;
    const seekBar = progressControl.seekBar;

    const spriteTip = document.createElement("div");
    spriteTip.className = "vjs-sprite-tooltip absolute -top-[106px] w-[176px] h-[99px] -translate-x-1/2 bg-base-300 border border-base-content/20 rounded shadow-lg pointer-events-none hidden bg-no-repeat z-30";
    seekBar.el().appendChild(spriteTip);

    player.on("loadedmetadata", () => {
      refreshSeekbarMarkers();
    });

    progressControl.el().addEventListener("mousemove", (e) => {
      const rect = seekBar.el().getBoundingClientRect();
      if (!rect.width || !state.cuts.length) return;

      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const duration = player.duration() || state.cuts[state.cuts.length - 1].end_time;
      const hoverTime = ratio * duration;

      setCellSpriteFrame(spriteTip, hoverTime);
      spriteTip.classList.remove("hidden");

      const halfW = 88;
      const rawX = ratio * rect.width;
      const clampedX = Math.max(halfW, Math.min(rect.width - halfW, rawX));
      spriteTip.style.left = `${clampedX}px`;
    });

    progressControl.el().addEventListener("mouseleave", () => {
      spriteTip.classList.add("hidden");
    });
  });

  player.on("timeupdate", () => {
    const t = player.currentTime();
    const idx = state.cuts.findIndex((c) => t >= c.start_time && t < c.end_time);
    if (idx !== -1 && idx !== state.currentIndex) {
      state.currentIndex = idx;
      const item = state.cuts[idx];
      if (dom.nowBadge) dom.nowBadge.textContent = "#" + item.id;
      if (dom.nowTitle) dom.nowTitle.textContent = item.title;
      if (dom.nowRange) dom.nowRange.textContent = `${item.source_range} (${item.duration_str})`;
      if (onTimeUpdateChapter) onTimeUpdateChapter(idx);
    }
  });

  document.getElementById("close-player-btn")?.addEventListener("click", () => {
    showPlayer(false);
  });

  dom.prevCutBtn?.addEventListener("click", () => seekCut("prev"));
  dom.nextCutBtn?.addEventListener("click", () => seekCut("next"));
  dom.splitHereBtn?.addEventListener("click", () => splitCurrentScene(onChaptersChanged));
  dom.exportSceneBtn?.addEventListener("click", () => exportActiveScene());

  window.addEventListener("resize", () => {
    if (dom.playerShell && !dom.playerShell.classList.contains("hidden")) {
      applyPlayerBounds();
    }
  });

  if (typeof window.interact !== "undefined" && dom.playerShell) {
    window.interact(dom.playerShell)
      .draggable({
        ignoreFrom: "button, .vjs-control-bar, input, .dropdown-content, .dropdown-menu",
        listeners: {
          move(event) {
            state.winState.x += event.dx;
            state.winState.y += event.dy;
            applyPlayerBounds();
          },
        },
      })
      .resizable({
        edges: { left: true, right: true, bottom: true, top: true },
        margin: 12,
        ignoreFrom: "button, .vjs-control-bar, .dropdown-content, .dropdown-menu",
        listeners: {
          move(event) {
            let newW = event.rect.width;
            if ((event.edges.top || event.edges.bottom) && !event.edges.left && !event.edges.right) {
              newW = (event.rect.height - 38) * (16 / 9);
            }
            newW = Math.max(260, Math.min(window.innerWidth - 20, newW));
            const prevW = state.winState.w;
            const prevH = prevW * (9 / 16) + 38;
            const newH = newW * (9 / 16) + 38;
            if (event.edges.left) {
              state.winState.x += prevW - newW;
            }
            if (event.edges.top) {
              state.winState.y += prevH - newH;
            }
            state.winState.w = newW;
            applyPlayerBounds();
          },
        },
      });
  }

  document.addEventListener("keydown", (e) => {
    if (dom.exportPopover?.open || dom.settingsPopover?.open) return;
    if (dom.playerShell?.classList.contains("hidden") && !isInPip()) return;
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      showPlayer(false);
      return;
    }
    const step = e.shiftKey ? 10 : 5;
    if (e.key === "[") {
      e.preventDefault();
      seekCut("prev");
    } else if (e.key === "]") {
      e.preventDefault();
      seekCut("next");
    } else if (e.key === "s" || e.key === "S") {
      e.preventDefault();
      splitCurrentScene(onChaptersChanged);
    } else if (e.key === "e" || e.key === "E") {
      e.preventDefault();
      exportActiveScene();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      player.currentTime(Math.min(player.duration() || Infinity, player.currentTime() + step));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      player.currentTime(Math.max(0, player.currentTime() - step));
    } else if (e.key === " " || e.key === "k") {
      e.preventDefault();
      if (player.paused()) player.play().catch(() => {});
      else player.pause();
    } else if (e.key === "f") {
      e.preventDefault();
      if (player.isFullscreen()) player.exitFullscreen();
      else player.requestFullscreen();
    }
  });
}
