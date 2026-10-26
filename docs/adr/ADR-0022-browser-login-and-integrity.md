# ADR-0022: Log in with a browser and refresh the integrity token

**Status:** Accepted (2026-10-26)

## Context

Twitch stopped issuing device codes to the `ANDROID_APP` client, so the device code login
([ADR-0010](ADR-0010-device-code-login.md)) cannot log in a new install. A token copied from the browser
([ADR-0021](ADR-0021-browser-token-login.md)) logs in as the web client, but the web client must send a
`Client-Integrity` header on `currentUser.dropCampaigns`, which only a browser page produces. Without it the
`Campaigns` operation returns `IntegrityCheckFailed` and the run ends.

Measured on 2026-10-26 against a real account: the integrity token is `v4.local` (encrypted), lives about 16
hours, and is bound to the `X-Device-Id` of the request that produced it, not to the user agent on the send side.
`gql.twitch.tv/integrity` answers with the token and an `expiration` timestamp. A headless browser's token is
rejected, because the default headless user agent names `HeadlessChrome`; a real (not headless) browser's token,
and a headless browser's token with the user agent set to a normal Chrome string, are accepted.

The owner asked for a login that works for a new install and keeps working for days without the user copying a
token every 16 hours.

## Decision

1. **The Login Form opens a browser.** A "Log in with browser" button runs the browser engine, which opens a
   visible browser on the inventory page. The user signs in and solves any challenge there. The engine reads the
   `auth-token` cookie once it appears and the integrity token from the page's next `/integrity` response. The app
   checks the token with `GET https://id.twitch.tv/oauth2/validate`, which names its client
   ([tokencheck.md](../modules/tokencheck.md#in-the-login)), switches to that client for its user agent and client
   ID, and keeps the token in the `auth-token` cookie of `cookies.jar`. This is the only login the app offers.
2. **The app sends `Client-Integrity`.** `_AuthState.headers` adds the header on every GQL request while a token is
   held, with the `X-Device-Id` the token is bound to, read once so a refresh cannot split the two.
3. **A task renews the token before it expires.** `_integrity_loop` runs for the whole run. It sleeps until
   `INTEGRITY_MARGIN` (10 minutes) before the `expiration` the `/integrity` response gave, then refreshes, and
   waits `INTEGRITY_RETRY` (5 minutes) after a failure. A `failed integrity check` error during a request also
   refreshes the token once and retries the request. One browser runs at a time (`_integrity_lock`), so the task
   and the retry never start two.
4. **The refresh is invisible, and its method is set per platform.** Linux runs a real (not headless) browser
   under a throwaway virtual display with `xvfb-run`, so its user agent is the browser's own. Windows and macOS
   have no such display and cannot hide a real window, so they run the browser headless and set its user agent to
   the web client's string, because Twitch rejects the integrity token of the default headless user agent. This
   is the one place the app sets a user agent that is not the browser's own.
5. **The engine is two modules.** `browser.py` holds the decisions (find a browser, build the launch arguments,
   read the `/integrity` response, capture a login or a token) behind a `BrowserConnection`, so a fake connection
   tests it. `browsercdp.py` is the Chrome DevTools Protocol I/O. A `browser_path` setting runs a chosen browser
   instead of the first of Chrome, Edge, Chromium or Brave found on the `PATH`.

## Consequences

- **A browser is required to log in and to refresh.** With none installed, the login prints that none was found,
  and a refresh is logged and skipped. The browser runs with a throwaway profile that the engine removes.
- **Xvfb on Linux.** The refresh needs the `xvfb` package; without `xvfb-run` the refresh fails and the run ends
  at the next integrity error, then logs in again.
- **Traffic.** The refresh is one browser page load about every 16 hours and sends no app GQL, within the one hard
  rule ([ADR-0002](ADR-0002-twitch-traffic-budget.md)). A `failed integrity check` costs one extra browser run and
  one retry.
- **Secrets.** The integrity token and the `auth-token` are secrets. `redact` hides the `Client-Integrity` header
  and the cookie in logs ([ADR-0011](ADR-0011-secrets-in-logs.md)).
- **The riskiest assumption** is that Twitch keeps accepting the unattended refresh. The one request case is
  measured; the true unattended case is shown only by a run across a token's full life. If Twitch stops accepting
  it, every run ends at the integrity error after the token expires, and the restart wait doubles
  ([ADR-0006](ADR-0006-restart-after-fatal-error.md)).

## Alternatives rejected

- **Pasting the integrity token** by hand. It expires about every 16 hours, and a miner runs for days.
- **No integrity token** ([ADR-0021](ADR-0021-browser-token-login.md), its first form). The web token then fails
  the `Campaigns` operation and the run ends.
- **Headless with the user agent set on every platform.** Linux can run a real browser invisibly under Xvfb, so
  it does, and sets no user agent. Only Windows and macOS, which cannot, set one.
- **Reading the browser's own cookie store.** The engine runs its own browser and reads no other program's files.

## Related

- [ADR-0021](ADR-0021-browser-token-login.md): the token paste this record replaces, now superseded.
- [ADR-0010](ADR-0010-device-code-login.md), [ADR-0002](ADR-0002-twitch-traffic-budget.md),
  [ADR-0006](ADR-0006-restart-after-fatal-error.md), [ADR-0011](ADR-0011-secrets-in-logs.md).
- [browser.md](../modules/browser.md), [browsercdp.md](../modules/browsercdp.md),
  [twitch.md](../modules/twitch.md#login), [settings.md](../modules/settings.md).
