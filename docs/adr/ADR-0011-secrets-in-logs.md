# ADR-0011: Secrets are hidden at the log call

**Status:** Accepted (2026-10-20)

## Context

Three log calls print a whole request, response or websocket message. `Twitch.request` logs its arguments
(`Request:`) and each response (`Response:`) at DEBUG on the `TwitchDrops` logger, which `-vvvv` turns on.
`Websocket.send` logs each message it sends (`sent:`) at DEBUG on `TwitchDrops.websocket`, which `--debug-ws`
turns on at any `-v` count. `--log` writes both to `log.txt`, and both appear in the Output box.

Those values hold secrets: the OAuth access token in the `Authorization` header of every GQL request and of
the token check, in the `token` field of the revoke request and in the `auth_token` of every `LISTEN` and
`UNLISTEN` message; the device code of a login in progress, with which anyone can finish that login; a proxy
password in `settings.proxy`; and the cookies in a response's `Set-Cookie` headers. The token gives the same
access as `cookies.jar`. [troubleshooting.md](../troubleshooting.md#reporting-a-problem) asks users to send a
log with a problem report, and check 6 in [AGENTS.md](../../AGENTS.md#what-every-change-must-pass) forbids
secrets in logs. [Task 011](../refinements/tasks/011-login-token-in-debug-log.md) recorded the problem.

An error can show a secret too. When a proxy rejects a request, aiohttp raises `ClientHttpProxyError`, and
its text includes the proxy URL with the password. `Twitch.request` does not retry that error, so
`Twitch._await_restart` prints its traceback in the Output box and logs it, which `--log` writes to
`log.txt`. With restarts turned off, `main.py` prints the traceback in the Output box.

The log lines are f-strings, so a value is already text when a log handler receives it.

## Decision

1. **A log call that prints a request, a response or a websocket message passes the value through
   `redact()`** in `redact.py`. It returns a copy in which the value of each secret key is `<hidden>`, at any
   depth of dicts, lists and tuples, and in which a URL's password is `<hidden>`. The value that is sent is
   not changed.
2. **A secret is found by its key name**, compared lowercase. `SECRET_KEYS` holds `access_token`, `auth_token`,
   `authorization`, `cookie`, `device_code`, `password`, `proxy-authorization`, `refresh_token`,
   `set-cookie` and `token`. The code and aiohttp name these keys where they build the value, so the name
   is known before the value becomes text.
3. **The `Response:` line logs the status, the method, the URL and the redacted headers**, in place of the
   text of aiohttp's `ClientResponse`, which prints every header.
4. **The rest of each line stays.** The method, the URL, the other headers, the GQL operations and the
   websocket topics are what a report about a failed request needs.
5. **`Twitch.request` passes the request info of a `ClientHttpProxyError` through `redact()`** and raises
   the same error again. Its text then shows `<hidden>` for the proxy password. Its type and traceback do
   not change, so every `except` clause that catches it works as before. `redact()` returns an aiohttp
   `RequestInfo` as a `RequestInfo` with redacted URLs and headers, because its `Proxy-Authorization`
   header holds the password in base64.

## Consequences

- A new log call that prints a header, a request body, a cookie or a websocket message uses `redact()`.
  AGENTS.md check 6 states this.
- A secret under a key name that is not in `SECRET_KEYS` is logged until its name is added.
- Of the proxy errors checked in aiohttp 3.14.3 (a rejected request, a closed port, a rejected websocket
  connection), only `ClientHttpProxyError` shows the password in its text. `Websocket` logs a connection
  error without its text.
- The `repr` of an aiohttp connection error shows the proxy URL and password of its connection. A log call
  prints such an error's class and text, never its `repr`, as `ImageCache.get` does for a failed download.
- `--debug-gql` still writes Twitch's GQL responses on `TwitchDrops.gql`. They hold account data but not the login
  token, and [gql-operations.md](../runbooks/gql-operations.md) says not to share that output.
- `redact()` runs for every request at every log level, because Python builds an f-string before the logger
  checks the level. It copies the arguments, which costs little next to the request, and it adds no request to
  Twitch.

## Alternatives rejected

- **A logging filter that replaces the current token's value in every record.** It needs each secret's value
  at run time, misses a value it was not given (a proxy password, a cookie, the device code of an earlier try),
  and works on text that the f-string has already built.
- **Raising an app exception in place of `ClientHttpProxyError`.** `Channel` catches `MinerException` and
  `RequestException` around some requests, so those clauses would start to catch a proxy error that they
  let through now.
- **Hiding passwords in the text of every traceback.** Each place that prints or logs a traceback would need
  the change, and a log call formats the traceback inside `logging`.
- **Removing the three log lines.** They are the only record of what the app sent and received.
- **Leaving the lines to a level that users do not set.** `-vvvv` is listed for users in troubleshooting.md, and
  `--debug-ws` turns its logger on at any `-v` count.

## Related

- [redact.md](../modules/redact.md), [twitch.md](../modules/twitch.md#requests),
  [websocket.md](../modules/websocket.md) and [main.md](../modules/main.md), which sets the log levels.
- [ADR-0010](ADR-0010-device-code-login.md): the login, the token and `cookies.jar`.
- Task [011](../refinements/tasks/011-login-token-in-debug-log.md) (the token in debug logs).
