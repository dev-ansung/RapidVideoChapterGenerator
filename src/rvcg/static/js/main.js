import { state, initStateFromBoot } from "./state.js";
import { initStatusRevealBtn } from "./api.js";
import { initPlayer } from "./player.js";
import { renderGallery, initGalleryControls, highlightActiveCard } from "./gallery.js";
import { initPicker, loadDirectory, startScan } from "./picker.js";
import { initSettingsAndExport } from "./settings.js";

function bootstrapApp() {
  initStateFromBoot();
  initStatusRevealBtn();
  initPlayer(
    () => highlightActiveCard(),
    () => renderGallery()
  );
  initGalleryControls(() => {});
  initPicker(() => renderGallery());
  initSettingsAndExport();

  loadDirectory(state.currentDir).then(() => {
    if (state.currentVideoPath) {
      startScan(state.currentVideoPath, false);
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrapApp);
} else {
  bootstrapApp();
}
