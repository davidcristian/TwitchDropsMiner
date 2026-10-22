# Runbook: updating a GQL operation, the client ID or the user agent

The app reads and changes Twitch data through GQL persisted queries. A persisted query is a query that Twitch
stores. A request names it by its operation name and the SHA-256 hash of its text, and sends no query text. When
Twitch changes a query, it stops accepting the old hash, and the feature that uses it fails. This runbook finds
the new hash and writes it into `constants.py`. The last section covers the client ID and the user agent that
every request sends. The module contracts are in [constants.md](../modules/constants.md) and
[twitch.md](../modules/twitch.md), and the request budget that a test run must respect is in
[ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md).

Upstream often fixes a broken operation first. Look for a new commit on DevilXD/TwitchDropsMiner before you
search for the hash yourself, and bring it in with [upstream-fixes.md](upstream-fixes.md).

## How an operation is defined

`GQL_QUERIES` in `constants.py` maps a key to a `GQLPersistedQuery(name, sha256, *, variables=None)`:

- the key, such as `"Campaigns"`, is what the code looks up, as in `GQL_QUERIES["Campaigns"]`, before it
  passes the entry to `Twitch.gql_request`. It does not change when Twitch changes the query;
- `name` is Twitch's operation name, such as `"ViewerDropsDashboard"`;
- `sha256` is the hash, 64 lowercase hex characters;
- `variables` are the defaults. A value written as `...` must be set by the caller through `with_variables`,
  which raises `RuntimeError: Unspecified variable: '<name>'` when the caller leaves it out.

## What a broken operation looks like

For an outdated hash, Twitch returns an error whose message is `PersistedQueryNotFound`. `Twitch.gql_request`
retries such a request once, after at least 5 seconds, and logs this line in the Output box, even without `-v`:

```text
ERROR: Retrying a PersistedQueryNotFound for ViewerDropsDashboard
```

The name at the end is the operation name, not the key. A `service error` gets the same single retry. One such
line followed by a normal run is a temporary error at Twitch. The operation is broken when the line appears on
every run.

When the retry fails too, `gql_request` raises `GQLException` with the `errors` list from Twitch's response.
Most callers do not handle it, so the run ends as a fatal error. The Output box shows `Fatal error encountered:`
and a traceback that ends in `exceptions.GQLException`, or in `exceptions.MinerException: Game: <slug>` for
`GameDirectory`. Then it shows `Restarting automatically at <time>...`, or `Application Terminated.` when
"Restart after a crash after" is set to "Never (stay stopped)". A restart fails the same way until the hash is
fixed, and each restart begins with a full reload
([task 019](../refinements/tasks/019-restart-runs-a-full-reload.md)). A call with an outdated hash sends 2
requests, and the rate limiter counts both.

A failure in the watch loop, such as an outdated `PlaybackAccessToken` hash, first shows
`ERROR: Exception in _watch_loop task` and its traceback. The lines above and the restart follow.

When Twitch changes the variables or the response of an operation, the error differs: a `GQLException` with
another message, or a `KeyError` or `TypeError` where the code reads the response. The steps below cover both
cases; step 2 of the update covers the variables.

To see every GQL request and response, add `--debug-gql` to the command. `--help` does not list it. It logs the
operations and Twitch's responses on the `TwitchDrops.gql` logger, and the responses contain your account data, so
do not share that output. At `-vvvv`, `Twitch.request` also logs each request and response, with the token
and other secrets shown as `<hidden>` ([redact.md](../modules/redact.md)).

## Find the current hash

1. Find the key and the operation name in `constants.py`. With the name from the log line:

   ```bash
   grep -n -B1 '"ViewerDropsDashboard"' constants.py
   ```

   Most entries have a comment that says what the operation returns.
2. Open <https://www.twitch.tv> in a browser and log in.
3. Open the developer tools (F12) and their Network tab. Type `gql.twitch.tv` in the filter box.
4. Open the Twitch page that shows the data the operation returns, for example the drops inventory at
   <https://www.twitch.tv/drops/inventory> or the campaigns at <https://www.twitch.tv/drops/campaigns>.
5. Click each `gql` request and open its request payload. Find the operation whose `operationName` is the name
   from step 1.
6. Copy `extensions.persistedQuery.sha256Hash`, and keep the payload's `variables` open for the next part.

If Twitch renamed the operation, no request has the old name. Look for a request that returns the same data,
and take its `operationName` as well.

## Update `constants.py`

1. Replace the hash, the second argument of the entry.
2. Compare the entry's `variables` with the payload's. Add a variable that the website sends and the entry
   lacks. Use the website's value, or `...` when the caller must set it; then every caller must pass it. List
   the callers by key:

   ```bash
   grep -n 'GQL_QUERIES\["Campaigns"\]' *.py
   ```

3. If Twitch renamed the operation, replace the name, the first argument. Keep the key.
4. Print the payload the app sends and compare it with the browser's payload:

   ```bash
   env/bin/python -c "from constants import GQL_QUERIES; print(GQL_QUERIES['Campaigns'])"
   ```

Then check that every hash has the right form. This prints `[]`, or the keys whose hash is malformed:

```bash
env/bin/python -c "
import re
from constants import GQL_QUERIES
print([k for k, v in GQL_QUERIES.items()
       if not re.fullmatch('[0-9a-f]{64}', v['extensions']['persistedQuery']['sha256Hash'])])
"
```

Last, run the checks in [AGENTS.md](../../AGENTS.md#what-every-change-must-pass).

## Check the result

Only Twitch can confirm the fix, and only with a login, because every GQL request the app sends includes the
account's OAuth token. Without a login, report the fix as unverified.

1. Start the app once with `env/bin/python main.py -vvv`.
2. Check that the Output box shows no `Retrying a PersistedQueryNotFound` line and no
   `Fatal error encountered:`.
3. Check that the feature works again. For `Inventory`, `Campaigns` and `CampaignDetails`, the Inventory tab
   lists campaigns; for `GameDirectory`, the Channels list on the Main tab fills.

Do not restart the app to repeat the test. Each start runs a full reload, which can cost thousands of requests.

## Commit

The subject names the operation by its key, for example:

```text
fix(constants): update the Campaigns GQL hash
```

The scope is `constants` because the change stays in `constants.py`. Drop the scope when a caller changes too.
A body is optional; when you write one, name the error, for example "Twitch returns
PersistedQueryNotFound for the old hash, so the inventory reload fails."

## The client ID and the user agent

`ClientType` in `constants.py` holds four `ClientInfo` entries: `WEB`, `MOBILE_WEB`, `ANDROID_APP` and
`SMARTBOX`. Each has a `CLIENT_URL`, a `CLIENT_ID` and a user agent or a list of them. From a list, `ClientInfo`
picks one at random when `constants.py` is imported, so once per run. `Twitch.__init__` sets
`self._client_type` to `ClientType.ANDROID_APP`, and no code reads the other three entries. The app sends the
client ID in the `Client-Id` header and in the login requests, and the user agent in the `User-Agent` header.

- **The user agent.** No code checks it, and no error message names it. Upstream updates the version numbers in
  these strings from time to time, in commits named `User agent update`. Bring those in with
  [upstream-fixes.md](upstream-fixes.md). Only a change to the `ANDROID_APP` list changes what the app sends.
- **The client ID.** A new `CLIENT_ID` in `ANDROID_APP`, or a switch of `_client_type` to another entry, logs
  every user out once. For a new `CLIENT_ID`, `_AuthState._validate` compares the client ID that Twitch reports
  for the saved token with `CLIENT_ID`; when they differ, it logs `Cookie client ID mismatch`, deletes
  `cookies.jar` and starts the login again. After a switch to an entry with another `CLIENT_URL`, the jar has no
  token for that URL, so the login starts without that check. Say so in the pull request, because every user
  sees it. [ADR-0010](../adr/ADR-0010-device-code-login.md) states the login decision.
