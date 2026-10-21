# `redact.py`

**Purpose.** Hides the login token and other secrets in a value before a log call prints it. Six log calls use
it: the `Request:` and `Response:` lines of `Twitch.request`, the `sent:` line of `Websocket.send`, the
`received:` line of `Websocket._gather_recv`, and the warnings of `Websocket._handle_recv` about a message of an
unknown type or a malformed one.
`Twitch.request` also passes the request info of a `ClientHttpProxyError` through it before it raises the
error again, because the error's text shows the proxy URL with its password. It passes the URL of its retry
message in the Output box through it too, because the usher URL has the playback token in its query.
[ADR-0011](../adr/ADR-0011-secrets-in-logs.md) gives the reasons.

## Public contract

- `redact(value)` returns a copy of `value`:
  - a mapping (a dict, a GQL operation, aiohttp's response headers) becomes a plain dict. The value of each key
    whose lowercase name is in `SECRET_KEYS` is `HIDDEN`, and every other value is redacted in the same way.
  - an aiohttp `RequestInfo` becomes a `RequestInfo` with its `url`, `headers` and `real_url` redacted. Its
    headers become a plain dict.
  - a list or a tuple becomes a list or a tuple of redacted items.
  - a `yarl.URL` gets `HIDDEN` as its password, when it has one, and as the value of each query parameter
    whose lowercase name is in `SECRET_KEYS`, such as the `token` of the usher URL. yarl writes `HIDDEN` as
    `%3Chidden%3E`. The rest of the URL keeps its encoded text, and a URL with nothing to hide is returned as
    it is.
  - any other value is returned as it is. So is a URL given as a `str`.
- `HIDDEN` is `"<hidden>"`.
- `SECRET_KEYS` is the set of key and query parameter names whose values are hidden: `access_token`,
  `auth_token`, `authorization`, `cookie`, `device_code`, `password`, `proxy-authorization`, `refresh_token`,
  `set-cookie` and `token`. `sig`, the signature that goes with the playback token, is not in it
  ([ADR-0011](../adr/ADR-0011-secrets-in-logs.md) says why).

## Invariants

- `redact` never changes its argument, because the same value is sent to Twitch.
- Keys are compared lowercase, so a header matches whatever case the code or aiohttp gives its name.
- A query is split at each `&` and a parameter name is decoded as yarl reads a query, so `%74oken` matches
  `token` as it does in the request that is sent.
- A mapping with a repeated key, such as response headers with two `Set-Cookie` lines, becomes a dict with one
  entry for that key. The result is for a log line to read, not for code to use.
- A GQL operation becomes a plain dict with the same text, because `GQLQuery` and `GQLPersistedQuery` are dict
  subclasses without their own `__repr__`.

**Dependencies.** `yarl`. No module of this repo. It finds aiohttp's `RequestInfo` by its type name and fields
rather than importing aiohttp, because the CI test job does not install aiohttp.
