// The keychain password is kept in memory only. It is never written to
// localStorage/sessionStorage and never logged.
let keychainPassword = null;

function savePassword() {
    const input = document.getElementById("askPasswordDialogInput");
    keychainPassword = input.value;
    // Do not leave the plaintext password sitting in the DOM.
    input.value = "";
    $("#askPasswordDialog").modal("hide");
}

eel.expose(askPassword);
// eel serializes the return value of an exposed function synchronously
// (see eel.js: it sends `_exposed_functions[name](...args)` straight to JSON),
// so it cannot await a Promise. This must stay synchronous.
function askPassword(message) {
    if (!keychainPassword) {
        // Nothing in memory - prompt the user so the next attempt succeeds.
        showPasswordDialog();
    }
    return keychainPassword;
}

function resetPassword() {
    keychainPassword = null;
}

function showPasswordDialog() {
    // Always start blank; never pre-fill with the current password.
    document.getElementById("askPasswordDialogInput").value = "";
    $("#askPasswordDialog").modal("show");
}

$(document).ready(() => {
    // One-time migration/cleanup: earlier versions persisted the plaintext
    // keychain password here. Purge it from disk. This is not storage.
    localStorage.removeItem("keychainPassword");

    // The password is no longer persisted, so ask for it up front.
    if (!keychainPassword) {
        showPasswordDialog();
    }
});
