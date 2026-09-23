#!/usr/bin/env python3
import eel
import logging

from lib import findmy_backend
from lib.trackers import DEFAULT_WITHIN_LAST_HOURS, get_tracker_locations

# Authentication happens once, out-of-band, via `python tools/findmy_login.py`,
# which writes the session file that lib.findmy_backend restores. The web UI
# never asks for a password.
LOGIN_HINT = (
    "Apple account is not set up. Run `python tools/findmy_login.py` in a "
    "terminal to sign in, then retry."
)


@eel.expose
def get_locations(trackers: list, hours: float = DEFAULT_WITHIN_LAST_HOURS):
    # eel cannot await Promises (eel.js serializes the return value of an
    # exposed function directly), so this must stay synchronous.
    # Never log tracker private keys.
    logging.debug(
        "get_locations: %d tracker(s) over the last %s hours: %s",
        len(trackers),
        hours,
        [tracker.get("name") for tracker in trackers],
    )
    try:
        # get_tracker_locations() already opens a single account_session() and
        # issues one batched Apple query for all keys, so there is nothing to
        # gain from managing the session here.
        return get_tracker_locations(trackers, hours)
    except findmy_backend.AccountNotConfiguredError:
        logging.exception("get_locations failed: no Apple account configured")
        raise RuntimeError(LOGIN_HINT) from None
    except findmy_backend.AccountStateError as exc:
        logging.exception("get_locations failed: unusable Apple session")
        raise RuntimeError(
            "Saved Apple session is unusable (%s). Run "
            "`python tools/findmy_login.py` to sign in again." % exc
        ) from None
    except Exception:
        logging.exception("get_locations failed")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html')
