function getSelectedDocsVersion(pathname) {
  if (!pathname) {
    pathname = document.location.pathname
  }
  let parts = pathname.split('/').filter(item => item !== "");
  if (parts.length === 1) {
    if (parts[0] === PROJECT) {
      // '/ape/' (return 'stable')
      return "stable";
    } else {
      // '/latest/' (return 'latest')
      return parts[0];
    }
  } else if (parts[0] === PROJECT) {
    // '/ape/latest/more' (return 'latest')
    return parts[1];
  } else {
    // '/latest/more' (return 'latest')
    return parts[0]
  }
}

$(document).ready(function () {
  // Version picker logic
  let current = getSelectedDocsVersion();
  $("option[value='" + current + "']").attr("selected", "selected");
  $("select").change(function () {
    if (this.value === "") {
      return false;
    }
    let current = getSelectedDocsVersion();
    let selected = $(this).val();
    $("option[value='" + selected + "']").attr("selected", "selected");
    window.location = document.URL.replace(current, selected);
  });
});
