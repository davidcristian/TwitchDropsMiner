# ADR-0010: Login by device code with the Android app client

**Status:** Accepted (2026-10-25)

## Context

The app mines on one Twitch account and keeps the login between runs. In the OAuth device code flow, the app
asks Twitch for a short code, the user enters it on the Twitch activation page in a browser where they are
logged in, and the app receives a token for the account. The app never sees the password.

The login comes from the original project. "First release" (2021-12-03) logged in with the password through
`https://passport.twitch.tv/login`, the code that is `_AuthState._login` in upstream's `twitch.py`. "Implement
SmartTV OAuth2 login flow" (2022-12-23) added `_oauth_login` and replaced the one call of `_login` with it, so from
then on the device code flow was the only login the app ran, until the token login of
[ADR-0021](ADR-0021-browser-token-login.md). "Change client type to android app" (2024-08-05) set the
current client, "Automatically clear the jar and delete the cookie file for re-auth" (2024-09-15) replaced the error
that the client ID check had raised since 2022-12-24 with a new login, and "Implement the auth token invalidation
button" (2026-07-02) added `Invalidate`. None of these commits has a message body, so the original project left no
written reason for the flow or for a client.
`ClientType`, the `Invalidate` handler and the device code flow work as upstream's do today, except that a device
response without a code does not end the run. Upstream's `_AuthState` also keeps `_login`, with no caller.

## Decision

1. **The device code flow is the login of the `Login` button.** `_AuthState._log_in` calls `_oauth_login` when
   the cookie jar has no `auth-token` cookie for `https://www.twitch.tv`. `_oauth_login`:
   1. Calls `LoginForm.ask_login`. The Output box shows "Please log in to continue.", and the call returns
      when the user presses `Login`. It returns a token that the user enters with `Use token` instead, which
      `_oauth_login` returns with no device code request ([ADR-0021](ADR-0021-browser-token-login.md)).
   2. Reads the device ID when it has none, as decision 4 describes, then POSTs the client ID and an empty
      `scopes` to `https://id.twitch.tv/oauth2/device`. The response has a device code, a user code, a polling
      `interval`, a lifetime `expires_in` and the activation page. When the status is not 200 or one of these
      fields is missing, it logs a warning, prints "The login could not get a code from Twitch:" with Twitch's
      `message`, or the status without one, and starts again at step 1
      ([devicecode.md](../modules/devicecode.md)). So each press sends one device request.
   3. Calls `LoginForm.ask_enter_code`, which shows the user code, and 4 seconds later the browser opens the
      activation page.
   4. POSTs the device code to `https://id.twitch.tv/oauth2/token` every `interval` seconds. The code comment
      says: "200 means success, 400 means the user haven't entered the code yet". On 200 it keeps the
      `access_token`. From one request timeout before the lifetime ends, `Twitch.request` raises
      `RequestInvalid`, and the flow starts again at step 1, so the next code waits for the next press.

2. **The client is `ClientType.ANDROID_APP`.** `Twitch.__init__` sets `_client_type` to it, and each login starts
   with it. A token of another `ClientType` entry switches `_client_type` to that entry
   ([ADR-0021](ADR-0021-browser-token-login.md)). Its `CLIENT_ID` is `kd1unb4b3q4t58fwlpcbzcbnm76a8fp`, its
   `CLIENT_URL` is `https://www.twitch.tv`, and its user agent is one of seven Twitch Android app strings, picked at
   random once per process. The aiohttp session sends the user agent of `_client_type` with every request. The
   device code, token, revoke and GQL requests send the client ID, and the GQL requests add
   `Authorization: OAuth <token>`.

3. **The token is kept in `cookies.jar`.** After a login, `_log_in` sets the cookies `auth-token` (the access
   token) and `persistent` (the user ID) for `https://www.twitch.tv`, and `_validate` saves the aiohttp cookie jar
   to `cookies.jar` next to the app. The next run takes the token from that cookie and logs "Restoring session from
   cookie". `_oauth_login` keeps only the token response's `access_token`, and no code refreshes a token.

4. **Each run checks the token at its start.** `_log_in` GETs `https://id.twitch.tv/oauth2/validate`, which
   gives the client ID and the user ID, then `_validate` GETs the `CLIENT_URL` of the token's client, whose
   `unique_id` cookie is the device ID. It does so when `access_token` or `user_id` is missing, which is at the
   start of each run, because `Twitch.shutdown` calls `_auth_state.clear()`. On the validate response:
   - **401:** it logs "Restored session is invalid", clears every cookie of `www.twitch.tv`, and asks the
     Login Form for a login.
   - **A `client_id` of no `ClientType` entry:** it logs "Restored session is of an unknown client", clears
     the jar, deletes `cookies.jar`, and asks the Login Form for a login. The `client_id` of another entry
     switches the app to that entry ([ADR-0021](ADR-0021-browser-token-login.md)).

   Any other response raises `RequestException`, a fatal error
   ([ADR-0006](ADR-0006-restart-after-fatal-error.md)).

5. **`Invalidate` logs out.** The Help tab's button (`HelpTab._invalidate_token`), enabled once a login has
   finished, POSTs the client ID of `_client_type`, which is the token's client, and the token to
   `https://id.twitch.tv/oauth2/revoke`. On 200 it calls `_AuthState.invalidate(delete_cookies=True)`, which removes
   the token and the user ID, clears the jar and deletes `cookies.jar`. Whatever the status, it then sets
   `State.RESTART`, so `_run` raises `ReloadRequest` and `Twitch.run` starts a new run, which logs in again. On
   another status it logs "Failed to invalidate the auth token", and the new run restores the same session from the
   cookie.

6. **There is no password login.** The app has no code for `https://passport.twitch.tv/login`, a CAPTCHA or
   a 2FA code, and the Login Form has no username, password or 2FA entries. Any error during the device code
   flow other than a device response without a code is a fatal error like any other, with the same restart
   delay ([ADR-0006](ADR-0006-restart-after-fatal-error.md)). A change that upstream makes to its `_login` is
   left out when its commit is brought in
   ([upstream-fixes.md](../runbooks/upstream-fixes.md#when-the-pick-conflicts)).

## Consequences

- **The login requests are not GQL,** so the GQL limiter does not apply to them
  ([ADR-0002](ADR-0002-twitch-traffic-budget.md)). A run with a saved token sends 2 GETs. A login also sends 1
  POST for a code at each `Login` press, then 1 POST every `interval` seconds until the code is entered or
  expires. The values in the code comment, `interval` 5 and `expires_in` 1800, give at most 360 polls.
- **A new `CLIENT_ID` of `ANDROID_APP` logs its users out once.** At the next start, the validate endpoint
  reports the old client ID, which no `ClientType` entry has, and the user logs in again. A switch of the client
  that `Twitch.__init__` sets to an entry with another `CLIENT_URL` logs every user out once too, because the jar
  has no token for that URL. `_log_in` compares only the client ID, so a new user agent alone does not make it
  delete a saved login.
- **Only `_validate` checks that the token still works,** so a token that stops working during a run is found
  only at the start of a later run.
- **The code is requested after the `Login` press,** because its lifetime counts from that request. The app
  can wait for the press for any time, such as after a start with the computer while nobody is there, and the
  code it shows is still valid. A code that expires before the user enters it needs another press.
- **Twitch has rejected the device code request of the `ANDROID_APP` client** since about 2026-09-18. It
  returns an error instead of a code, and reports of it show the message "invalid client". So the `Login`
  button gets no code, and a new login takes a token copied from the browser
  ([ADR-0021](ADR-0021-browser-token-login.md)). The app prints Twitch's message at each `Login` press, and the
  run goes on. Upstream sends the same request and gets the same error.
- **`cookies.jar` gives access to the account,** as the README's caution says, and it is gitignored. A log line
  shows the token as `<hidden>` ([ADR-0011](ADR-0011-secrets-in-logs.md)).
- **The README's note on the "New Login" email** says that the app presents itself to Twitch as Chrome. The
  upstream README has said so since 2024-09-15, when the client was already `ANDROID_APP`. Decision 2 gives
  today's.
- **`Invalidate` starts a new run,** which costs one full reload (ADR-0002). A press during a fetch starts it
  when the fetch ends ([ADR-0017](ADR-0017-state-requests.md)).

## Alternatives rejected

- **Bringing back the password login.** It has had no caller since 2022-12-23. Its comments quote two Twitch
  errors: 5023, "client is not supported for this feature", and 5027, "client blocked from this operation".
- **Keeping the password login with no caller.** 270 lines in `twitch.py`, `gui.py` and four other modules,
  and 10 strings that every language file translates, described a login and a CAPTCHA wait that the app never
  ran. Removing them makes an upstream change to `_login` conflict, but upstream last changed it on 2024-08-04
  ([task 010](../refinements/tasks/010-unreachable-password-login.md)).
- **Another `ClientType` entry for the device code login.** Nothing here shows that one works better, and
  [ADR-0021](ADR-0021-browser-token-login.md) gives why the `SMARTBOX` client is not used.
- **Sending the device request again without a press.** While Twitch rejects the client, every request gets the
  same error, and nobody may be there to enter a code.

## Related

- [twitch.md](../modules/twitch.md#login), [devicecode.md](../modules/devicecode.md),
  [twitchapi.md](../modules/twitchapi.md#client-identities), [gui.md](../modules/gui.md#the-window) and
  [ARCHITECTURE.md](../ARCHITECTURE.md#data-flow).
- [troubleshooting.md](../troubleshooting.md#logging-in): logging in, logging out and switching accounts.
  [gql-operations.md](../runbooks/gql-operations.md#the-client-id-and-the-user-agent): changing the client ID.
- [ADR-0002](ADR-0002-twitch-traffic-budget.md), [ADR-0006](ADR-0006-restart-after-fatal-error.md),
  [ADR-0017](ADR-0017-state-requests.md) (a press during a fetch), and
  [ADR-0009](ADR-0009-watch-method.md) for the watch requests, which send the same user agent.
- Tasks [010](../refinements/tasks/010-unreachable-password-login.md) (the password login),
  [011](../refinements/tasks/011-login-token-in-debug-log.md) (the token in debug logs) and
  [014](../refinements/tasks/014-hard-coded-strings.md) (the translation of the line with the user code).
