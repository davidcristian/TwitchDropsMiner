# A device code can expire before the Login press

**Status:** open
**Area:** twitch (login), gui (login form)
**Origin:** Found on 2026-10-18 while the docs were written, [ADR-0010](../../adr/ADR-0010-device-code-login.md)
**Verified:** 2026-10-18

`_AuthState._oauth_login` in `twitch.py` sends `POST https://id.twitch.tv/oauth2/device` first, and sets
`expires_at` from the `expires_in` of the response (1800 seconds, as the code comment gives it). Only then
does it call `LoginForm.ask_enter_code` in `gui.py`, which waits in `wait_for_login_press` until the user presses
`Login`, prints the code, waits 4 seconds and opens the activation page. The code's lifetime therefore counts
from the request, not from the press.

When the user presses `Login` more than 30 minutes after the request, for example after the app started with the
computer while nobody was there, the Output box shows a code that has already expired, and the browser opens its
activation page. The first poll of `POST https://id.twitch.tv/oauth2/token` passes `invalidate_after=expires_at`
to `Twitch.request`, which raises `RequestInvalid` before it sends anything. `_oauth_login` catches it, requests a
new code and waits for another `Login` press. So the code the user typed on the activation page is never used,
and the user has to press `Login` a second time and enter a second code.

Confirmed by reading the code path: `_oauth_login` (the device request, then `ask_enter_code`, then the poll
loop with `invalidate_after`), `LoginForm.ask_enter_code` and the `invalidate_after` check in `Twitch.request`.
Not run, because it needs the Twitch login endpoints.

A fix requests the device code after the `Login` press: `ask_enter_code` splits into a wait for the press and a
step that prints the code and opens the page, and `_oauth_login` sends the device request between them. It
costs no extra request. An expired code still requests a new one as it does now.

## History

- 2026-10-18: Opened. The agent that wrote ADR-0010 found the order of the device request and the `Login` press.
