# The password login and its CAPTCHA handling cannot run

**Status:** done 2026-10-19
**Area:** twitch (login), main, gui, constants, translate
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md#login)
**Verified:** 2026-10-19

The app logs in only through the OAuth device code flow. `_AuthState._validate` in `twitch.py` calls
`_AuthState._oauth_login` and no other login. `_AuthState._login`, the password login through
`https://passport.twitch.tv/login`, has no caller. It is the only code that raises `CaptchaRequired` or
`LoginException`, and `_oauth_login` raises neither.

So this code never runs, or runs only to build widgets that the window never shows:

- **`twitch.py`:** `_AuthState._login` (138 lines), and `SkipExtraJsonDecoder` and `SAFE_LOADS`, which only
  `_login` uses. The `CaptchaRequired` branch of `Twitch._await_restart` and the counter `_captcha_denials`,
  which `Twitch.__init__` sets to 0 and `_run` sets back to 0 after each login.
- **`constants.py`:** `CAPTCHA_RESTART_DELAY` (1 hour) and `CAPTCHA_RESTART_MAX` (12 hours). Only that branch
  reads them.
- **`main.py`:** the `except CaptchaRequired` branch of `main()`, which prints the CAPTCHA message and sets
  exit code 1.
- **`gui.py`:** `LoginData`, `LoginForm.ask_login` and `LoginForm.clear`. Only `_login` and `ask_login` call
  them. `LoginForm.__init__` still creates the Username, Password and 2FA code entries, but their `grid` calls
  are commented out, so the window never shows them.
- **`translate.py`:** `login.error_code`, `login.incorrect_login_pass`, `login.incorrect_email_code`,
  `login.incorrect_twofa_code`, `login.email_code_required` and `login.twofa_code_required`, which only `_login`
  reads. `error.captcha`, which only the two CAPTCHA branches read. `gui.login.username`, `gui.login.password`
  and `gui.login.twofa_code`, the placeholders of the hidden entries. All 20 language files in `lang/` translate
  these strings. The four `login.chrome` strings are in [022](022-unused-code.md).

Some docs describe this code as if it runs. Decision 6 of
[ADR-0006](../../adr/ADR-0006-restart-after-fatal-error.md) states a CAPTCHA restart schedule of 1, 2, 4 and 8
hours, then 12 hours. [`manual.txt`](../../../manual.txt), which ships with every release, says that exit code
1 is "Exit caused by the CAPTCHA or a Fatal Exception". The module docs ([twitch.md](../../modules/twitch.md),
[exceptions.md](../../modules/exceptions.md), [main.md](../../modules/main.md) and
[constants.md](../../modules/constants.md)) already say that it cannot run.

## How it was confirmed

A script parsed the 21 files `*.py` and `gamelib/*.py` with the `ast` module. It listed every definition and
call of `_login`, `_oauth_login` and `ask_login`, every `getattr` call with the string `"_login"`, and every
`raise` of `CaptchaRequired` or `LoginException`. The output:

```
def ask_login: gui.py:581
def _oauth_login: twitch.py:128
def _login: twitch.py:202
raise LoginException: twitch.py:339
raise CaptchaRequired: twitch.py:335
call ask_login: twitch.py:225
call _oauth_login: twitch.py:398
raise LoginException: twitch.py:325
```

No line calls `_login`, and the one call of `ask_login` is inside `_login`. `git grep` for each translation key
above finds reads only in the places listed.

## Effect

None at run time, because the app never runs this code. A reader of the code, of ADR-0006 or of `manual.txt`
has to work out that the CAPTCHA schedule, the exit code text and the login strings describe nothing the app
does. `twitch.py` is 1849 lines against the 300 line cap ([005](005-modules-over-the-line-cap.md)), and about
150 of them are this login. The 20 language files keep translations of strings that the app never shows.

## How it came about

`git log -S'await self._login()' -- twitch.py` finds two commits of the original project. "First release"
(2021-12-03) added the call, and "Implement SmartTV OAuth2 login flow" (2022-12-23) replaced it with
`await self._oauth_login()` and commented out the `grid` calls of the three entries. The password code stayed.
The original project still has it, and last changed `_login` in "Exceptions cleanup" (2024-08-04), which added
its final `raise LoginException`. The comments in `_login` quote two error responses from Twitch: 5023,
"client is not supported for this feature", and 5027, "client blocked from this operation".

This project added the CAPTCHA restart schedule in "Restart automatically after a fatal error" (2026-08-25,
found with `git log -S'_captcha_denials'`), three years and eight months after the last call of `_login` was
removed. Its commit message treats a CAPTCHA denial as a case that happens.

## What a fix involves

Both choices send no Twitch request, and the device code login stays as it is.

- **Remove the dead path.** Delete everything listed above, and the keys from the `TypedDict` classes and
  `default_translation`. The language files can keep the keys: `merge_json` drops a key that
  `default_translation` lacks when a file loads ([023](023-language-file-keys-dropped.md)). `_await_restart`
  then has one schedule. ADR-0006 changes: decision 6, and the CAPTCHA parts of its context, of decisions 3, 5
  and 7, of its consequences and of its alternatives. Decision 7 still applies, because a restart can fall after
  midnight. Exit code 1 in `manual.txt` becomes "a fatal exception", and the module docs change in the same
  commit. An upstream change to `_login` would then conflict when it is brought in
  ([upstream-fixes.md](../../runbooks/upstream-fixes.md)), but upstream has not changed it since 2024.
- **Keep it, with a written reason.** The reason is a plan to bring back a password login. A comment above
  `_login` states it, ADR-0006 says that decision 6 applies only once `_login` has a caller, and `manual.txt`
  stops naming the CAPTCHA. The code stays in `twitch.py`, which is over the cap. Its
  `logger.info(str(login_response))` then passes the response through `redact`
  ([ADR-0011](../../adr/ADR-0011-secrets-in-logs.md)), because a successful response holds the token.

## History

- 2026-10-18: Opened. Checking the login section of twitch.md and ADR-0006 against the code showed that the
  password login has no caller, and an `ast` scan of the modules confirmed it.
- 2026-10-19: Closed. The dead path was removed: everything listed above, `CaptchaRequired` and
  `LoginException` in `exceptions.py`, the 10 strings and their `TypedDict` keys. The language files keep their
  translations, which [023](023-language-file-keys-dropped.md) now lists. ADR-0010 and ADR-0006 state the new
  decision, and `manual.txt` names only a fatal exception for exit code 1. `git log -L` on upstream's `_login`
  found a later change than the one named above, and that paragraph now names it.
