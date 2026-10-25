# ADR-0021: Login with a token copied from the browser

**Status:** Accepted (2026-10-25)

## Context

Since about 2026-09-18, Twitch has rejected the device code request of the `ANDROID_APP` client, the only login
that [ADR-0010](ADR-0010-device-code-login.md) had. Twitch returns "invalid client" instead of a code, so a new
install cannot log in, and only a token that `cookies.jar` already holds works.

A user who logs in to <https://www.twitch.tv> in a browser has an OAuth token for the account: the browser keeps
it in the `auth-token` cookie of `www.twitch.tv`. Twitch issued it to its web client, whose client ID is the
`CLIENT_ID` of `ClientType.WEB`. `GET https://id.twitch.tv/oauth2/validate` returns the `client_id` and
`user_id` of a token, so the app can tell which client a token belongs to.

The owner asked for a manual way in: the user copies that cookie's value by hand and pastes it into the app.
The check of a saved token deleted `cookies.jar` whenever the token's client ID was not that of `ANDROID_APP`,
so it would have deleted a token of the web client at the next start.

## Decision

1. **The Login Form takes a token.** While it asks for a login, the Login Form has the masked entry `Token:`
   and the button `Use token` below the `Login` button. A press of `Use token` with a value ends the wait as
   a `Login` press does, and `_oauth_login` returns the value as the token, with no device code request.
   `tokencheck.entered_token` removes whitespace and control characters from it, and the entry is emptied.
2. **Each token gets one check.** `_log_in` sends the token check with `Authorization: OAuth <token>` for the
   token of `cookies.jar`, for an entered token and for one from the device code flow.
   [tokencheck.md](../modules/tokencheck.md#in-the-login) gives what each result does. For an entered token: a
   401 prints "Twitch did not accept the token." and asks again; a `client_id` of no `ClientType` entry prints
   that the token belongs to a client the app does not know, and asks again.
3. **The app acts as the client of the token.** When the `client_id` is the `CLIENT_ID` of a `ClientType`
   entry, `_use_client` switches `_client_type` to that entry, with its user agent as the session's default
   header. The switch is part of `get_auth`, which `_run` awaits before its first GQL request. Each login starts
   with `ANDROID_APP`, so the device code flow and the cookie lookup do not depend on the previous run.
4. **A saved token of a known client is kept.** At a start, a saved token of any `ClientType` entry switches
   the app to that entry, and `cookies.jar` stays. A saved token of an unknown client still clears the jar and
   deletes `cookies.jar`.
5. **The token is kept as the device code login keeps its token,** in the `auth-token` cookie of
   `https://www.twitch.tv` in `cookies.jar`. The token check names the client at every start, so no
   `settings.json` key stores it.
6. **The app does not touch the browser or the integrity check.** It reads no browser file or cookie store,
   does not start or drive a browser, and creates or sends no integrity token (`Client-Integrity`). When Twitch
   answers an operation sent with the web client with an integrity error, such as "failed integrity check", the
   app reports it through the error paths it has: `gql_request` raises `GQLException`, which ends the run as a
   fatal error ([ADR-0006](ADR-0006-restart-after-fatal-error.md)). It does nothing to get past the check.

## Consequences

- **Traffic.** An entered token costs one token check, plus what a login costs otherwise. A run with a saved token
  sends 2 GETs: the check, then the page whose `unique_id` cookie is the device ID. The page GET follows the check,
  so the device ID comes from the URL of the token's client, and in the device code flow it follows the `Login`
  press. These requests are not GQL ([ADR-0002](ADR-0002-twitch-traffic-budget.md)).
- **The token is the browser's session.** Logging out of Twitch in that browser ends it, and the next start
  gets a 401 and asks for a login. `Invalidate` in the app revokes it with the web client ID, which logs the
  browser out too.
- **The token works like a password.** The entry masks it, `cookies.jar` keeps it, and no log line shows it:
  `redact` hides the `Authorization` header and the `auth-token` cookie name
  ([ADR-0011](ADR-0011-secrets-in-logs.md)).
- **The riskiest assumption** is that Twitch answers the GQL operations of the app, sent with the web client ID
  and no integrity token, as it answers those of the Android app client. Only a real login can show it. If
  Twitch requires the integrity token, every run that sends the operation ends with the error, and the restart
  wait doubles up to 60 minutes.
- **A token of `MOBILE_WEB` or `SMARTBOX` is handled the same way.** Their `CLIENT_URL` is not `www.twitch.tv`, so the
  device ID comes from their own page, and the cookies stay at `www.twitch.tv`.
- **A rejected token from the device code flow** prints the message and waits for the next press, like an
  entered one. A check response with another status, or a 200 without a user ID, raises `RequestException` at
  once, with no second check.
- **A change of the `ANDROID_APP` client ID** logs a user of that client out once, because the old ID is
  of no `ClientType` entry. A token of another entry is not affected.

## Alternatives rejected

- **The device code login with the `SMARTBOX` client.** Twitch still answers its device code request, but, as
  upstream's maintainer reports, that client gets no campaigns, so the miner would not start new campaigns.
- **Reading the token from the browser's cookie store, or driving a browser.** The owner ruled it out. The app
  would read the files of other programs.
- **Creating an integrity token** to pass the check that Twitch may apply to the web client. The owner ruled it
  out.
- **A `settings.json` key with the client type.** The token check returns the client ID at every start, and a
  key would need a name that can never change ([ADR-0007](ADR-0007-kept-identifiers.md)).

## Related

- [ADR-0010](ADR-0010-device-code-login.md): the device code login, `cookies.jar` and `Invalidate`.
- [tokencheck.md](../modules/tokencheck.md), [twitch.md](../modules/twitch.md#login) and
  [gui.md](../modules/gui.md#the-window) (the Login Form).
- [troubleshooting.md](../troubleshooting.md#logging-in): how to copy the `auth-token` cookie.
- [ADR-0002](ADR-0002-twitch-traffic-budget.md), [ADR-0006](ADR-0006-restart-after-fatal-error.md) and
  [ADR-0011](ADR-0011-secrets-in-logs.md).
