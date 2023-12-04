const PASSWORD_KEY="keychainPassword";

function savePassword() {
    const content = document.getElementById("askPasswordDialogInput").value;
    console.log(content);
    localStorage.setItem(PASSWORD_KEY, content);
    $("#askPasswordDialog").modal("hide");
}

eel.expose(askPassword);
function askPassword(message) {
    return localStorage.getItem(PASSWORD_KEY);
}

function resetPassword() {
    return localStorage.removeItem(PASSWORD_KEY);
}

function showPasswordDialog() {
    document.getElementById("askPasswordDialogInput").value = localStorage.getItem(PASSWORD_KEY);
    $("#askPasswordDialog").modal("show");
}

$(document).ready(() => {
    if (!localStorage.getItem(PASSWORD_KEY)) {
       showPasswordDialog();
    }
});


