# ADR-0011: Secrets are hidden at the log call

**Status:** Accepted (2026-10-18)

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

The log lines are f-strings, so a value is already text when a log handler receives it.

## Decision

1. **A log call that prints a request, a response or a websocket message passes the value through
   `redact()`** in `redact.py`. It returns a copy in which the value of each secret key is `<hidden>`, at any
   depth of dicts, lists and tuples, and in which a URL's password is `<hidden>`. The value that is sent is
   not changed.
2. **A secret is found by its key name**, compared lowercase. `SECRET_KEYS` holds `access_token`, `auth_token`,
   `authorization`, `cookie`, `device_code`, `password`, `refresh_token`, `set-cookie` and `token`. The code
   names these keys where it builds the value, so the name is known before the value becomes text.
3. **The `Response:` line logs the status, the method, the URL and the redacted headers**, in place of the
   text of aiohttp's `ClientResponse`, which prints every header.
4. **The rest of each line stays.** The method, the URL, the other headers, the GQL operations and the
   websocket topics are what a report about a failed request needs.

## Consequences

- A new log call that prints a header, a request body, a cookie or a websocket message uses `redact()`.
  AGENTS.md check 6 states this.
- A secret under a key name that is not in `SECRET_KEYS` is logged until its name is added.
- `--debug-gql` still writes Twitch's GQL responses on `TwitchDrops.gql`. They hold account data but not the login
  token, and [gql-operations.md](../runbooks/gql-operations.md) says not to share that output.
- `redact()` runs for every request at every log level, because Python builds an f-string before the logger
  checks the level. It copies the arguments, which costs little next to the request, and it adds no request to
  Twitch.
- The password login logs Twitch's response to a failed login without `redact()`. It has no caller
  ([task 010](../refinements/tasks/010-unreachable-password-login.md)).

## Alternatives rejected

- **A logging filter that replaces the current token's value in every record.** It needs each secret's value
  at run time, misses a value it was not given (a proxy password, a cookie, the device code of an earlier try),
  and works on text that the f-string has already built.
- **Removing the three log lines.** They are the only record of what the app sent and received.
- **Leaving the lines to a level that users do not set.** `-vvvv` is listed for users in troubleshooting.md, and
  `--debug-ws` turns its logger on at any `-v` count.

## Related

- [redact.md](../modules/redact.md), [twitch.md](../modules/twitch.md#requests),
  [websocket.md](../modules/websocket.md) and [main.md](../modules/main.md), which sets the log levels.
- [ADR-0010](ADR-0010-device-code-login.md): the login, the token and `cookies.jar`.
- Tasks [011](../refinements/tasks/011-login-token-in-debug-log.md) (the token in debug logs) and
  [010](../refinements/tasks/010-unreachable-password-login.md) (the password login).
