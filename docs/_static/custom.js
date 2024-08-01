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

  // Cookbook Onboard (AI Assistant). 
  // API key is public so it's fine to just hardcode it here.
  var COOKBOOK_PUBLIC_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NmFhY2QzYjZiYmI2MmQwOGY0ZjYzNzgiLCJpYXQiOjE3MjI0Njk2OTEsImV4cCI6MjAzODA0NTY5MX0.Xw4JO3X3T19NOGqPnsz_DYDEBdsxNYM9JkZK4k8ADs8";
  var element = document.getElementById("__cookbook");
  if (!element) {
    element = document.createElement("div");
    element.id = "__cookbook";
    element.dataset.apiKey = COOKBOOK_PUBLIC_API_KEY;
    document.body.appendChild(element);
  }

  var script = document.getElementById("__cookbook-script");
  if (!script) {
    script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/@cookbookdev/docsbot/dist/standalone/index.cjs.js";
    script.id = "__cookbook-script";
    script.defer = true;
    document.body.appendChild(script);
  }
});
