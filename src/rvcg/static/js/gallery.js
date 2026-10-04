import { state, dom, fmtHms, fmtHmsMs, setCellSpriteFrame, cutDotColorClass, formatMechanismSummary } from "./state.js";
import { recalcChapters, setStatus } from "./api.js";
import { openAt } from "./player.js";

export function highlightActiveCard() {
  document.querySelectorAll(".chapter-card").forEach((el) => {
    const isActive = Number(el.dataset.index) === state.currentIndex;
    el.classList.toggle("ring-2", isActive);
    el.classList.toggle("ring-primary", isActive);
  });
}

export function matchesFilter(item) {
  if (!state.searchQuery) return true;
  const q = state.searchQuery.normalize("NFC").toLowerCase();
  return (
    item.id.toLowerCase().includes(q) ||
    item.title.normalize("NFC").toLowerCase().includes(q) ||
    item.source_range.toLowerCase().includes(q)
  );
}

export function renderGallery(onChaptersChanged) {
  if (!dom.gallery) return;
  dom.gallery.innerHTML = "";
  let visibleCount = 0;

  state.cuts.forEach((item, index) => {
    if (!matchesFilter(item)) return;
    visibleCount++;

    const card = document.createElement("article");
    const isActive = index === state.currentIndex;
    card.className = `chapter-card card bg-base-200 border border-base-content/10 shadow-sm transition-all overflow-hidden hover:border-primary/40 hover:shadow-md ${isActive ? "ring-2 ring-primary" : ""}`;
    card.dataset.index = index;

    const header = document.createElement("div");
    header.className = "card-header flex items-center justify-between px-3 py-2 border-b border-base-content/10 bg-base-300/40 cursor-pointer select-none";
    header.addEventListener("click", () => openAt(index, item.start_time, highlightActiveCard));

    const hLeft = document.createElement("div");
    hLeft.className = "card-header-left flex items-center gap-2 flex-1 min-w-0 mr-2";

    const cutDot = document.createElement("span");
    cutDot.className = `cut-dot inline-block w-2.5 h-2.5 rounded-full shrink-0 ${cutDotColorClass(item.cut_kind || "start")}`;
    cutDot.dataset.tippyContent = item.cut_detail || "";

    const badge = document.createElement("span");
    badge.className = "badge badge-neutral badge-sm font-mono font-bold tracking-tight shrink-0";
    badge.textContent = "#" + item.id;

    const titleInput = document.createElement("input");
    titleInput.className = "input input-ghost input-xs font-semibold flex-1 min-w-0 hover:bg-base-100/50 focus:bg-base-100 focus:input-bordered text-xs rounded transition-colors";
    titleInput.value = item.title;
    titleInput.addEventListener("click", (e) => e.stopPropagation());
    titleInput.addEventListener("change", async () => {
      const next = state.cuts.map((c, idx) => ({
        start_time: c.start_time,
        end_time: c.end_time,
        title: idx === index ? titleInput.value : c.title,
        cut_kind: c.cut_kind,
        cut_detail: c.cut_detail,
      }));
      const res = await recalcChapters(next);
      if (res.ok) {
        state.cuts = res.chapters;
        setStatus("Unsaved edits", false);
        renderGallery(onChaptersChanged);
        if (onChaptersChanged) onChaptersChanged();
      }
    });

    hLeft.appendChild(cutDot);
    hLeft.appendChild(badge);
    hLeft.appendChild(titleInput);

    const hRight = document.createElement("div");
    hRight.className = "card-header-right flex items-center gap-2 shrink-0";

    const metaSpan = document.createElement("span");
    metaSpan.className = "text-[11px] text-base-content/60 font-mono tracking-tight shrink-0";
    metaSpan.innerHTML = `<span class="hidden sm:inline">${item.source_range} · </span><span>${item.duration_str}</span>`;
    hRight.appendChild(metaSpan);

    if (state.cuts.length > 1) {
      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-ghost btn-xs btn-circle text-base-content/40 hover:text-error hover:bg-error/10 transition-colors";
      delBtn.type = "button";
      delBtn.textContent = "✕";
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const next = state.cuts.map((c) => ({
          start_time: c.start_time,
          end_time: c.end_time,
          title: c.title,
          cut_kind: c.cut_kind,
          cut_detail: c.cut_detail,
        }));
        if (index === 0) {
          next[1].start_time = next[0].start_time;
          next[1].cut_kind = next[0].cut_kind;
          next[1].cut_detail = next[0].cut_detail;
        } else {
          next[index - 1].end_time = next[index].end_time;
        }
        next.splice(index, 1);
        const res = await recalcChapters(next);
        if (res.ok) {
          state.cuts = res.chapters;
          setStatus("Unsaved edits", false);
          renderGallery(onChaptersChanged);
          if (onChaptersChanged) onChaptersChanged();
        }
      });
      hRight.appendChild(delBtn);
    }

    header.appendChild(hLeft);
    header.appendChild(hRight);

    const grid = document.createElement("div");
    grid.className = "contact-grid grid grid-cols-3 grid-rows-3 aspect-video gap-0.5 bg-black/40 p-1 rounded-b-box overflow-hidden";

    const slots = item.cell_times.length >= 9 ? item.cell_times.slice(0, 9) : item.cell_times;
    slots.forEach((baseTime) => {
      const cell = document.createElement("div");
      cell.className = "grid-cell relative overflow-hidden bg-base-300 cursor-pointer rounded-xs bg-no-repeat transition-transform hover:scale-[1.02] hover:z-10";
      setCellSpriteFrame(cell, baseTime);

      const timeBadge = document.createElement("span");
      timeBadge.className = "cell-time absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/80 backdrop-blur-md text-[10px] text-white/90 font-mono shadow-sm border border-white/10 pointer-events-none";
      timeBadge.textContent = fmtHms(baseTime);
      cell.appendChild(timeBadge);

      let cellVideo = null;
      let rafId = null;

      cell.addEventListener("mouseenter", () => {
        if (cellVideo || !state.videoSrc) return;
        cellVideo = document.createElement("video");
        cellVideo.src = state.videoSrc;
        cellVideo.muted = true;
        cellVideo.playsInline = true;
        cellVideo.preload = "auto";
        cellVideo.className = "absolute inset-0 w-full h-full object-cover z-0";
        cellVideo.addEventListener("loadedmetadata", () => {
          if (!cellVideo) return;
          cellVideo.currentTime = baseTime;
          cellVideo.play().catch(() => {});
        });
        const tick = () => {
          if (!cellVideo) return;
          const ct = cellVideo.currentTime;
          if (ct >= baseTime + item.card_dur) {
            cellVideo.currentTime = baseTime;
          }
          timeBadge.textContent = fmtHmsMs(ct || baseTime);
          rafId = requestAnimationFrame(tick);
        };
        rafId = requestAnimationFrame(tick);
        cell.insertBefore(cellVideo, timeBadge);
      });

      cell.addEventListener("mouseleave", () => {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = null;
        if (cellVideo) {
          cellVideo.pause();
          cellVideo.removeAttribute("src");
          cellVideo.load();
          cellVideo.remove();
          cellVideo = null;
        }
        timeBadge.textContent = fmtHms(baseTime);
      });

      cell.addEventListener("click", (e) => {
        e.stopPropagation();
        openAt(index, baseTime, highlightActiveCard);
      });

      grid.appendChild(cell);
    });

    card.appendChild(header);
    card.appendChild(grid);
    dom.gallery.appendChild(card);
  });

  if (typeof window.tippy !== "undefined") {
    window.tippy(dom.gallery.querySelectorAll(".cut-dot"), {
      placement: "top",
      delay: [40, 0],
      maxWidth: 360,
      appendTo: () => document.body,
    });
  }

  const mechSummary = formatMechanismSummary(state.lastStats);
  const mech = mechSummary ? ` (${mechSummary})` : "";
  if (dom.countLabel) {
    dom.countLabel.textContent = `${visibleCount} / ${state.cuts.length} chapters${mech}`;
  }
}

export function initGalleryControls(onChaptersChanged) {
  document.getElementById("search-input")?.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.trim();
    renderGallery(onChaptersChanged);
  });

  document.querySelectorAll(".view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".view-btn").forEach((b) => b.classList.remove("btn-active"));
      btn.classList.add("btn-active");
      const isList = btn.dataset.view === "list";
      dom.gallery?.classList.toggle("grid-cols-1", isList);
      dom.gallery?.classList.toggle("md:grid-cols-2", !isList);
      dom.gallery?.classList.toggle("xl:grid-cols-3", !isList);
      dom.gallery?.classList.toggle("list-view", isList);
    });
  });
}
