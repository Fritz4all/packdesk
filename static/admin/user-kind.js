// User page: staff-only fields (admin language, role, superuser) are hidden for customers, and follow the
// "Kind" choice while the form is being filled in.
document.addEventListener("DOMContentLoaded", function () {
  var kind = document.getElementById("id_kind");
  if (!kind) return;
  var rows = ["id_admin_language", "id_role", "id_is_superuser"]
    .map(function (id) { var el = document.getElementById(id); return el && el.closest(".field-row"); })
    .filter(Boolean);
  function update() {
    rows.forEach(function (row) { row.hidden = kind.value === "customer"; });
  }
  kind.addEventListener("change", update);
  update();
});
