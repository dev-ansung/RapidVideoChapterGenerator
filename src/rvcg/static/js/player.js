import { state, dom, setCellSpriteFrame } from "./state.js";

export let player = null;

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
    if (dom.exportPopover?.open || dom.settingsPopover?.open || dom.splitModalPopover?.open) return;
    if (dom.playerShell?.classList.contains("hidden") && !isInPip()) return;
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      showPlayer(false);
      return;
    }
    const step = e.shiftKey ? 10 : 5;
    if (e.key === "ArrowRight") {
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
