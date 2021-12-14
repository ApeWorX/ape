function getSelectedDocsVersion() {
  return document.location.pathname
      .replace(PROJECT, "")
      .replaceAll("/", "");
}

$(document).ready(function () {
  // Version picker logic
  let current = getSelectedDocsVersion()
  $("option[value='" + current + "']").attr("selected", "selected");
  $("select").change(function () {
    if (this.value === "") {
      return false;
    }
    let current = getSelectedDocsVersion()
    let selected = $(this).val();
    $("option[value='" + selected + "']").attr("selected", "selected");
    window.location = document.URL.replace(current, selected);
  });
});
