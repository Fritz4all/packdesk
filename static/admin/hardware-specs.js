// Device page: only the specifications of the chosen device type are shown, and they follow the "Device type"
// choice while the form is being filled in.
document.addEventListener("DOMContentLoaded", function () {
  var type = document.getElementById("id_device_type");
  if (!type) return;
  var fields = Array.prototype.slice.call(document.querySelectorAll("[data-spec-types]"));
  var hint = document.querySelector("[data-spec-hint]");
  function update() {
    var shown = 0;
    fields.forEach(function (field) {
      var row = field.closest(".field-row") || field.parentElement;
      row.hidden = field.dataset.specTypes.split(",").indexOf(type.value) === -1;
      if (!row.hidden) shown++;
    });
    if (hint) (hint.closest(".field-row") || hint.parentElement).hidden = shown > 0;
  }
  type.addEventListener("change", update);
  update();
});
