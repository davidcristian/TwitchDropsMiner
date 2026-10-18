# Debug logs contain the login token

**Status:** done 2026-10-18
**Area:** twitch (requests), websocket, logging
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md#requests)
**Verified:** 2026-10-18

Two log calls write the OAuth access token, and the first of them also writes the device code of a login in
progress:

- **`Twitch.request` in `twitch.py` (line 1453)** logs `Request: (method=..., url=..., kwargs=...)` at DEBUG
  on the `TwitchDrops` logger. `kwargs` holds the request's headers and body:
  - every GQL request: `gql_request` passes `_AuthState.headers(gql=True)`, which contains
    `Authorization: OAuth <access_token>`.
  - the token check in `_AuthState._validate`: a GET of `https://id.twitch.tv/oauth2/validate` with the same
    header.
  - the `Invalidate` button: `HelpTab._invalidate_token` in `gui.py` posts the token as `data["token"]`.
  - the device code login: `_AuthState._oauth_login` polls `https://id.twitch.tv/oauth2/token` every
    `interval` seconds. The poll body holds only the client ID, the device code and the grant type. So until
    the code expires (`expires_in`, 1800 seconds in the code's example answer), anyone with the log line can
    send the same poll and receive the token once the user enters the code.
- **`Websocket.send` in `websocket.py` (line 333)** logs `sent: {message}` at DEBUG on the
  `TwitchDrops.websocket` logger. Each `LISTEN` and `UNLISTEN` message has the token in `data["auth_token"]`
  (`Websocket._handle_topics`, lines 220 and 236).

The `Response:` line of `Twitch.request` (line 1471) logs `str(response)`. aiohttp's
`ClientResponse.__repr__` prints every response header (checked in aiohttp 3.14.3; `requirements.txt` allows
3.9 and later 3.x), so a `Set-Cookie` header from Twitch is logged too. An example is the GET of
`https://www.twitch.tv` that sets the `unique_id` cookie. The `auth-token` cookie never comes from a response:
`_validate` writes it into the cookie jar itself (line 399).

The token is the value of the `auth-token` cookie in `cookies.jar`.
[troubleshooting.md](../../troubleshooting.md) says that anyone who has that file can use the Twitch account,
and AGENTS.md check 6 forbids secrets in logs.

## Which flags write it

`main.py` sets the levels. The count of `-v` picks `LOGGING_LEVELS[min(count, 4)]`: 3 (`-vvv`) is `CALL`, one
below INFO, and 4 (`-vvvv`) is DEBUG. `TwitchDrops.websocket` is set to DEBUG by `--debug-ws`, to INFO at
`-vvvv` without it, and otherwise inherits the `TwitchDrops` level. `--log` adds a `FileHandler` for `log.txt`
to `TwitchDrops`, and `GUIManager` adds the handler that writes each record to the Output box. Records of the
child loggers reach both handlers.

| Flags | `Request:` lines | `sent:` lines of the websocket |
| --- | --- | --- |
| `-vvv` or fewer | not written | not written |
| `-vvvv` | written, with the token and the device code | not written |
| `--debug-ws`, with any `-v` count | not written below `-vvvv` | written, with the token |
| `--debug-gql` alone | not written | not written |

`--debug-gql` writes the operations and Twitch's answers on `TwitchDrops.gql`. They contain account data but
not the token. [gql-operations.md](../../runbooks/gql-operations.md) already warns not to share either output.

## How it was confirmed

A script set up the loggers as `main.py` does for given flags, with a `FileHandler` in a temporary folder. It
called the real `Twitch.request` with a stub client whose `gui.close_requested` is True, so the call logs its
line and raises `ExitRequest` before it sends anything. It passed the headers from the real
`_AuthState.headers(gql=True)`, the `validate` header, the `revoke` body and a device code poll body, each with
a fake token. It then called the real `Websocket.send` with a stub socket and a `LISTEN` message. Lines that
contain the fake token or the fake device code:

```
-vvv:              0 lines in the file
-vvvv:             4 lines, token in 3 (GQL, validate, revoke), device code in 1
--debug-ws:        1 line, token in 1 (the LISTEN message)
-vvv --debug-ws:   1 line, token in 1
--debug-gql:       0 lines
```

The other log calls, listed with `git grep` on `logger`, `ws_logger` and `gql_logger`, write fixed text, names,
IDs, status codes, exceptions and the websocket messages that Twitch sends. None of them is passed a header, a
request body or the token. The `PlaybackAccessToken` answer that `--debug-gql` writes holds a playback token
for the watched stream, which is not the login token. The password login, which never runs
([010](010-unreachable-password-login.md)), logs Twitch's answer to a failed login.

## Effect

A user who follows [troubleshooting.md](../../troubleshooting.md#reporting-a-problem) and sends a log made with
`-vvv --log` sends no token. That page says to repeat `-v` "up to `-vvvv`", and a log or a screenshot of the
Output box made at `-vvvv`, or with `--debug-ws`, contains the token on many lines: at `-vvvv` every GQL
request writes one. Whoever reads it can send requests as that account until the token is revoked with
`Invalidate`. troubleshooting.md warns against sending a `-vvvv` log, but `--debug-ws` has no warning, and
nothing removes the token from the lines.

## How it came about

Both log lines come from the original project. The `Request:` line first appears in "Ensure connection error
cause is included" (2022-02-11), and the websocket `sent:` line in "Proper argparse and better logging system"
(2021-12-16), both found with `git log -S`.

## What a fix involves

Replace the secret values before they reach the log, in the log calls themselves:

- In `Twitch.request`, log a copy of `kwargs` in which the `Authorization` header and the `token` and
  `device_code` fields of `data` show a fixed text such as `<hidden>`. Log the response status and URL, and no
  `Set-Cookie` header.
- In `Websocket.send`, log a copy of the message without `data["auth_token"]`.

`twitch.py` and `websocket.py` are over the 300 line cap, so a shared helper goes in a new module, which
AGENTS.md asks for. A check calls both log paths with a fake token, as above, and fails when the token appears;
it fits the test suite of [003](003-test-suite.md). The docs that warn about `-vvvv` then change. The fix sends
no Twitch request.

## How it was closed

`redact.py` adds `redact()`, which returns a copy of a value with the value of each secret key, and a URL's
password, replaced by `<hidden>` ([ADR-0011](../../adr/ADR-0011-secrets-in-logs.md)). The `Request:` and
`Response:` lines of `Twitch.request` and the `sent:` line of `Websocket.send` pass their values through it. The
`Response:` line now logs the status, the method, the URL and the redacted headers. The fix also covers a proxy
password, which the `Request:` line logged with `settings.proxy` and which this task did not list.

The script described above, extended with a proxy URL that has a password and a response with a `Set-Cookie`
header, ran against the code before and after the fix. It exits 1 when a secret is in the log:

```
before -vvvv:            token in 3, device code in 1, proxy password in 1, cookie in 1   exit 1
before --debug-ws:       token in 1                                                     exit 1
after  -vvv:             0 lines                                                        exit 0
after  -vvvv:            0 secrets, each shown as <hidden>                              exit 0
after  --debug-ws:       0 secrets                                                      exit 0
after  -vvvv --debug-ws --debug-gql:  0 secrets                                         exit 0
```

## History

- 2026-10-18: Opened. While twitch.md was written, the `Request:` line was found to include the headers. Real
  calls of the log paths under each set of flags showed which flags write the token, and found the websocket
  line and the device code.
- 2026-10-18: Closed. `redact()` hides the secrets in the three log lines, and the before and after runs of the
  check above show no secret in the log after the fix.
