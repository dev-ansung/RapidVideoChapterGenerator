import { state } from "./state.js";
import { initStatusRevealBtn } from "./api.js";
import { initPlayer, highlightActiveCard } from "./player.js";
import { renderGallery, initGalleryControls } from "./gallery.js";
import { initPicker, loadDirectory, startScan } from "./picker.js";
import { initTrimModal } from "./trim-modal.js";
import { initSettingsAndExport } from "./settings.js";

document.addEventListener("DOMContentLoaded", () => {
  initStatusRevealBtn();
  initPlayer(
    () => highlightActiveCard(),
    () => renderGallery()
  );
  initGalleryControls(() => {});
  initPicker(() => renderGallery());
  initTrimModal();
  initSettingsAndExport();

  loadDirectory(state.currentDir).then(() => {
    if (state.currentVideoPath) {
      startScan(state.currentVideoPath, false);
    }
  });
});
