// PackDesk additions to the unfold admin theme.

// Collapsible inline rows: a row that was just added opens straight away.
document.addEventListener("formset:added", (event) => {
  const row = event.target.closest("[x-data]") || event.target;
  if (window.Alpine && row && row._x_dataStack) {
    window.Alpine.$data(row).openRow = true;
  }
});

// Sidebar sections: remember open/closed per section in this browser. Only a click is remembered;
// without one, the section of the current page is open (unfold's default).
const PD_NAV_KEY = "packdesk-nav-";

function pdNavInitial(key, activeDefault) {
  try {
    const saved = localStorage.getItem(PD_NAV_KEY + key);
    if (saved !== null) return saved === "1";
  } catch (e) {}
  return activeDefault;
}

function pdNavSave(key, open) {
  try { localStorage.setItem(PD_NAV_KEY + key, open ? "1" : "0"); } catch (e) {}
}

function pdNavAll(open) {
  document.querySelectorAll("[data-pd-nav]").forEach((section) => {
    if (window.Alpine) window.Alpine.$data(section).navigationOpen = open;
    pdNavSave(section.dataset.pdNav, open);
  });
}
