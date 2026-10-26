# `browser.py`

**Purpose.** A Twitch web `auth-token` passes most GQL, but the `Campaigns` operation needs a `Client-Integrity`
header that only a real browser page produces ([twitch.md](twitch.md#login)). This module holds the engine's
decisions: which browser to run, how to start it, how to read the `/integrity` response, and how to capture a
login or an integrity token. It drives a `BrowserConnection`, which [browsercdp.md](browsercdp.md) implements over
the Chrome DevTools Protocol, so a fake connection tests it without a real browser or Twitch.

## Public contract

- `find_browser(configured="", names=BROWSER_NAMES)` returns the browser path: `configured` when it is a file,
  else the first of `names` found on the `PATH`, else a browser at a standard install location on Windows (under
  `%ProgramFiles%` and the like) or macOS (`/Applications`), else `None`.
- `launch_args(port, profile, *, headless, user_agent="")` returns the browser arguments for a debugging port and
  a throwaway profile. `headless` adds `--headless=new`; a `user_agent` adds `--user-agent`. The last argument is
  the inventory page.
- `login_options()` and `refresh_options(user_agent)` return `LaunchOptions(headless, user_agent, xvfb)`. Login is
  a visible window with the browser's own user agent. A refresh on Linux is a real window under Xvfb with its own
  user agent; on Windows and macOS it is `--headless=new` with `user_agent`, because Twitch rejects the integrity
  token of the default headless user agent, which names `HeadlessChrome`.
- `capture_login(connection, timeout, poll=1.0)` opens the inventory page and waits for the `auth-token` cookie,
  which the user sets by logging in, then reads the integrity token of the page's next `/integrity` response. It
  returns `LoginResult(access_token, integrity)`, or `None` when no login arrives within `timeout` seconds.
- `capture_integrity(connection, access_token, timeout)` sets the `auth-token` cookie, opens the inventory page,
  and returns the `IntegrityToken(token, device_id, expires_at)` of the page's `/integrity` response, or `None`.
- `parse_integrity(body, device_id)` returns the `IntegrityToken` of an `/integrity` response body, or `None` when
  it has no string `token` and numeric `expiration`.
- `BrowserConnection` is the `Protocol` the engine drives: `set_cookie`, `navigate`, `next_event`,
  `response_body` and `cookies`. `browsercdp.CdpConnection` is the real one; tests pass a fake.

## Invariants

- The engine holds every decision; the only I/O is in the injected `BrowserConnection`.
- The integrity token is bound to the device ID of the request that produced it, so `capture_login` and
  `capture_integrity` return that device ID, which the caller sends with the token.
- `expires_at` is epoch milliseconds, read from the `/integrity` response, so the refresh is timed off it.

**Dependencies.** Repo modules: none. Otherwise the standard library only (`json`, `shutil`, `sys`).
