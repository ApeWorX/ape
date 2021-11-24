$(document).ready(function() {
    // version picker logic
    let currentDocsVersion = 'stable';
    let path = document.location.pathname.split("/");
    if(path.length >= 3) {
        currentDocsVersion = path[2];
    }
    $("option[value='" + currentDocsVersion + "']").attr("selected", "selected");
    $("select").change(function() {
        if(this.value === "") {
            return false;
        }
        let newUrl = document.URL.replace(PROJECT + "/" + currentDocsVersion, PROJECT + "/" + $(this).val());
        window.location = newUrl;
    });
});
