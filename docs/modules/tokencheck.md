# `tokencheck.py`

**Purpose.** Reads the response to the token check, `GET https://id.twitch.tv/oauth2/validate` with the header
`Authorization: OAuth <token>`, and finds the client type that a token belongs to. The login sends the check for
the token in `cookies.jar`, and for a token from the Login Form: one that the user entered, or one from the
device code login ([twitch.md](twitch.md#login)). With these functions, `LoginMixin._log_in` in
`twitch/login.py` switches the app to the client of the token, or asks for another token. The module sends no
request and needs neither Twitch nor a display.

## Public contract

- `CLIENT_TYPES` is the tuple of the `ClientInfo` entries of `ClientType`, in the order of its class body: `WEB`,
  `MOBILE_WEB`, `ANDROID_APP` and `SMARTBOX` ([twitchapi.md](twitchapi.md#client-identities)).
- `client_of(client_id, clients=CLIENT_TYPES)` returns the client of `clients` whose `CLIENT_ID` equals
  `client_id`, or None.
- `check_token(status, body, clients=CLIENT_TYPES)` returns a `TokenCheck(result, client, user_id)`. `body` is
  the JSON value of a 200 response and None for another status. `result` is a `TokenResult`:

  | Response | `result` | `client`, `user_id` |
  | --- | --- | --- |
  | 401 | `REJECTED` | None, 0 |
  | 200, `client_id` of a client in `clients`, `user_id` a whole number | `ACCEPTED` | that client, the user ID |
  | 200, a `client_id` of no client in `clients`, or none | `UNKNOWN_CLIENT` | None, 0 |
  | 200 without a `user_id` that is a whole number, 200 with a body that is not an object, any other status | `FAILED` | None, 0 |

  Twitch sends `user_id` as a string of digits; a number is accepted too.
- `entered_token(text)` returns the text of the Login Form's token entry without whitespace and control
  characters, which no token has. A pasted token can end with a newline, and aiohttp raises `ValueError` for a
  header value with a control character.

## In the login

`_log_in` sends one check for each token, and acts on the result:

| `result` | Token from `cookies.jar` | Token from the Login Form |
| --- | --- | --- |
| `ACCEPTED` | uses `client` from then on ([The client of the token](#the-client-of-the-token)), and keeps the token in `cookies.jar` | the same |
| `REJECTED` | logs "Restored session is invalid", clears the cookies of `https://www.twitch.tv`, and asks the Login Form | prints `login.token_rejected`, "Twitch did not accept the token.", and asks again |
| `UNKNOWN_CLIENT` | logs "Restored session is of an unknown client", calls `_AuthState.invalidate(delete_cookies=True)`, which clears the jar and deletes `cookies.jar`, and asks the Login Form | prints `login.unknown_client`, "The token belongs to a Twitch client that the app does not know.", and asks again |
| `FAILED` | raises `RequestException`, a fatal error ([twitch.md](twitch.md#restart-after-a-fatal-error)) | the same |

A 200 response that is not JSON, such as a network's login page, raises aiohttp's `ContentTypeError` before
`check_token` runs, and the fatal error shows `login.unexpected_content`. Each token the user enters costs one
check, and the app sends no check by itself, so a wrong token sends nothing more until the user enters another.

## The client of the token

`_use_client(client)` sets `Twitch._client_type` to `client` and the `User-Agent` default header of the aiohttp
session to its user agent. The code that builds a request or a URL reads them when it runs: the `Client-Id`,
`Origin` and `Referer` headers of the GQL requests, the user agent of every request and websocket,
`Channel.url` and the client ID of the revoke request of `Invalidate`. When the new client has another `CLIENT_URL`, it removes `device_id`, and `_validate` reads it after
the login from the `unique_id` cookie of that URL, so the run sends one GET of the page as before.

Each login starts with `_use_client(_login_client)`, the client type that `Twitch.__init__` set,
`ClientType.ANDROID_APP`. So the device code flow uses that client after a run with another one, and the
`auth-token` and `persistent` cookies stay at its URL, `https://www.twitch.tv`, where the next start looks for
them. The switch happens in `get_auth`, which `_run` awaits before it sends any GQL request
([ADR-0021](../adr/ADR-0021-browser-token-login.md)).

**Dependencies.** `twitchapi`, for `ClientType` and `ClientInfo`. The standard library otherwise.
