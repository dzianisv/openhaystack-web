// The macOS-keychain password dialog is gone: authentication now happens once,
// out-of-band, via `python tools/findmy_login.py`. This file only keeps the
// one-time cleanup below.
//
// WHY THIS MUST STAY: builds older than the FindMy.py migration persisted the
// user's macOS login password in localStorage in PLAINTEXT under
// "keychainPassword". That value survives upgrades and sits in the browser's
// on-disk storage forever unless something removes it. Deleting this purge
// would strand the leaked secret on every existing install. Keep it.
$(document).ready(() => {
    localStorage.removeItem("keychainPassword");
});
