// PackDesk additions to the unfold admin theme.

// Collapsible inline rows: a row that was just added opens straight away.
document.addEventListener("formset:added", (event) => {
  const row = event.target.closest("[x-data]") || event.target;
  if (window.Alpine && row && row._x_dataStack) {
    window.Alpine.$data(row).openRow = true;
  }
});
