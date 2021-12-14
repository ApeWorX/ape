$(document).ready(function () {
  // Version picker logic
  let current = document.location.pathname.replaceAll("/", "")
  $("option[value='" + current + "']").attr("selected", "selected");
  $("select").change(function () {
    if (this.value === "") {
      return false;
    }
    let current = document.location.pathname.replaceAll("/", "")
    let selected = $(this).val();
    $("option[value='" + selected + "']").attr("selected", "selected");
    window.location = document.URL.replace(current, selected);
  });
});
