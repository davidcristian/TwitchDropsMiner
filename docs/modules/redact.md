# `redact.py`

**Purpose.** Hides the login token and other secrets in a value before a log call prints it. Three log calls
use it: the `Request:` and `Response:` lines of `Twitch.request` and the `sent:` line of `Websocket.send`.
[ADR-0011](../adr/ADR-0011-secrets-in-logs.md) gives the reasons.

## Public contract

- `redact(value)` returns a copy of `value`:
  - a mapping (a dict, a GQL operation, aiohttp's response headers) becomes a plain dict. The value of each key
    whose lowercase name is in `SECRET_KEYS` is `HIDDEN`, and every other value is redacted in the same way.
  - a list or a tuple becomes a list or a tuple of redacted items.
  - a `yarl.URL` with a password gets `HIDDEN` as its password, which yarl writes as `%3Chidden%3E`.
  - any other value is returned as it is.
- `HIDDEN` is `"<hidden>"`.
- `SECRET_KEYS` is the set of key names whose values are hidden: `access_token`, `auth_token`, `authorization`,
  `cookie`, `device_code`, `password`, `refresh_token`, `set-cookie` and `token`.

## Invariants

- `redact` never changes its argument, because the same value is sent to Twitch.
- Keys are compared lowercase, so a header matches whatever case the code or aiohttp gives its name.
- A mapping with a repeated key, such as response headers with two `Set-Cookie` lines, becomes a dict with one
  entry for that key. The result is for a log line to read, not for code to use.
- A GQL operation becomes a plain dict with the same text, because `GQLQuery` and `GQLPersistedQuery` are dict
  subclasses without their own `__repr__`.

**Dependencies.** `yarl`. No module of this repo.
