# `devicecode.py`

**Purpose.** Reads the response to the device code request, `POST https://id.twitch.tv/oauth2/device`, which is
the first request of the login ([twitch.md](twitch.md#login)). Since about 2026-09-18, Twitch returns an error
instead of a code for the `ANDROID_APP` client ID ([ADR-0010](../adr/ADR-0010-device-code-login.md)). With these
functions, `_AuthState._oauth_login` reports such a response in the Output box, and the run goes on. The module
sends no request and needs neither Twitch nor a display.

## Public contract

- `read_json(body)` returns the value of a response body, given as bytes, read as JSON. It returns None for an
  empty body, a body that is not JSON, such as an HTML error page, and bytes that no JSON encoding decodes.
- `device_code_error(status, body)` returns None when `status` is 200 and `body` is a dict with every field in
  `CODE_FIELDS`: `device_code`, `user_code`, `interval`, `verification_uri` and `expires_in`, which
  `_oauth_login` reads. Otherwise it returns the `message` of `body` when that is a string that is not empty,
  and else the status as text, such as `"403"`.

## In the login

`_oauth_login` reads the body with `read_json`, so a body that is not JSON raises nothing. When
`device_code_error` returns a message, `_oauth_login`:

1. logs the warning "Twitch sent no device code" with the status and the body, through `redact`, which the
   Output box shows with `-v`;
2. prints `login.no_code` with the message, such as "The login could not get a code from Twitch: invalid
   client";
3. waits for the next `Login` press, and sends one device request after it.

So each press sends one device request and no other request, and the app sends none by itself. The run goes
on, without the restart wait of a fatal error ([twitch.md](twitch.md#restart-after-a-fatal-error)).

**Dependencies.** None: the standard library only.
