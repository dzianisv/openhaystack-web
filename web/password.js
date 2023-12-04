const PASSWORD_KEY="keychainPassword";

function savePassword() {
    localStorage.setItem(PASSWORD_KEY, $("#askPasswordDialogInput").value);
    $("#askPasswordDialog").modal("hide");
}

function askPassword(message) {
    return localStorage.getItem(PASSWORD_KEY)
}

function resetPassword() {
    return localStorage.removeItem(PASSWORD_KEY)
}

function showPasswordDialog() {
    $("#askPasswordDialogInput").value = localStorage.getItem(PASSWORD_KEY);
    $("#askPasswordDialog").modal("show");
}

$(document).ready(() => {
    if (!localStorage.getItem(PASSWORD_KEY)) {
       showPasswordDialog();
    }
});


