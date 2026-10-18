# `--version` and `--help` show their output as an error

**Status:** open
**Area:** main
**Origin:** Found on 2026-10-18 while the docs were written, [main.md](../../modules/main.md#command-line-flags)
**Verified:** 2026-10-18

`main.py` defines `Parser`, a subclass of `argparse.ArgumentParser`. Its `_print_message` writes argparse's
output to a `StringIO`, and its `exit` always shows that text with
`messagebox.showerror("Argument Parser Error", ...)`, whatever the exit status is. argparse calls `exit` with
status 2 for a flag it does not know, and with status 0 after `--help` and `--version`. So the version number
and the usage text both appear in a dialog titled "Argument Parser Error", with the error icon.

## How it was confirmed

- A script took the `Parser` class from the source of `main.py` with the `ast` module and ran it with a stub
  `messagebox` that prints its arguments, on Python 3.12:
  - `--version`: `showerror(title='Argument Parser Error', message='v16.dev\n')`, exit status 0.
  - `--help`: the same title with the usage text, exit status 0.
  - `--bogus`: the same title with the usage and `unrecognized arguments: --bogus`, exit status 2.
- `main.py --version` and `main.py --help` were run from a copy of the repo under Xvfb, and a screenshot was
  taken of each. Both dialogs show the red error icon next to the text. Xvfb runs no window manager, so the
  screenshots show no title bar.

## Effect

A user who asks for the version or the help sees an error dialog, and may think the app is broken.
[troubleshooting.md](../../troubleshooting.md) tells the user that the dialog is not an error after `--version`,
and says nothing about `--help`. The title is English text written in `main.py`, not a key in `translate.py`.

## How it came about

From `git log -S` on `main.py`. Both commits come from the original project. "Proper argparse and better
logging system" (2021-12-16) added `--version`. "An error is now shown for incorrect arguments passed"
(2022-02-15) added the dialog for an unknown flag, and `--help` and `--version` reach the same `exit`.

## What a fix involves

In `Parser.exit`, show `messagebox.showinfo` with a neutral title, such as the app name in `WINDOW_TITLE`, when
the status is 0, and keep `showerror` for any other status. A new title goes into `translate.py` as a key, as
AGENTS.md asks. It still shows in English here: `main()` sets the language after the settings load, and the
settings need the parsed flags. The same commit updates the "Argument Parser Error" line in
[troubleshooting.md](../../troubleshooting.md) and the flag section of [main.md](../../modules/main.md).

Cost: no Twitch requests. The parser exits before the app connects.

## History

- 2026-10-18: Opened. Found while the docs were written. Running the `Parser` class with a stub dialog and
  running `main.py` under Xvfb confirmed the error title and icon for `--version` and `--help`. The second
  claim checked with it, that the Proxy label's "(requires restart)" is wrong, did not hold. With stub objects
  for the session, `Twitch.request` passed the new proxy on the next request, but
  `Websocket._backoff_connect` reads the proxy once when its connection task starts and passed the old value
  on a reconnect. So a change reaches PubSub only after a restart.
