"use strict";

document.querySelectorAll("[data-back-link]").forEach((link) => {
  link.addEventListener("click", (event) => {
    // Preserve opening in a new tab and use the home link for direct visits.
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    if (window.history.length > 1) {
      event.preventDefault();
      window.history.back();
    }
  });
});
