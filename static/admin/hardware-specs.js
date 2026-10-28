// Device page: only the specifications of the chosen device type are shown, and they follow the "Device type"
// choice while the form is being filled in.
document.addEventListener("DOMContentLoaded", function () {
  var type = document.getElementById("id_device_type");
  if (!type) return;
  var fields = Array.prototype.slice.call(document.querySelectorAll("[data-spec-types]"));
  function update() {
    fields.forEach(function (field) {
      var row = field.closest(".field-row") || field.parentElement;
      row.hidden = field.dataset.specTypes.split(",").indexOf(type.value) === -1;
    });
  }
  type.addEventListener("change", update);
  update();
});
