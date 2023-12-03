function savePassword() {
    localStorage.setItem("keychainPassword", document.getElementById("askPasswordDialogInput").value);
    $("#askPasswordDialog").modal("hide");
}

function askPassword(message) {
    return localStorage.getItem("keychainPassword")
}

$(document).ready(() => {
    if (!localStorage.getItem("keychainPassword")) {
        $("#askPasswordDialog").modal("show");
    }
});


