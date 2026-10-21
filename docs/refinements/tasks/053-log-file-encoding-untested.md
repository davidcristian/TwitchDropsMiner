# No test checks that `log.txt` is written in UTF-8

**Status:** done 2026-10-22
**Area:** main, tests
**Origin:** The suite tests for the earlier fixes in `gui.py`, `websocket.py` and `utils.py`, which found no
function in `main.py` that a test can call to create the log file handler
**Verified:** 2026-10-22

With `--log`, `main()` in `main.py` adds a `logging.FileHandler(LOG_PATH, encoding="utf-8")` to the
`TwitchDrops` logger ([main.md](../../modules/main.md#logging)). Without the encoding, a line with a character
outside the code page of the locale, such as a Korean channel name, is lost. No suite test checks the encoding:

- `main()` is defined inside `if __name__ == "__main__":`, so a test cannot import it.
- A test that runs `main.py` starts the whole app: a Tk root, the lock on `lock.file` and `log.txt` in the app's
  folder, which is the repo when it runs from source, and a login to Twitch.

## What a fix involves

Move the creation of the handler into a function that takes the path and returns the handler, in a module that
`main.py` imports after the version check, and test that a line with a character outside cp1252 reads back from
the file. `utils.py` is over the line cap, so the function goes in a new module or in one under the cap. A test
can then also check `FILE_FORMATTER` on the handler.

Twitch requests: none.

## History

- 2026-10-21: Opened. The tests of the other fixes were added to the suite, and this one was left without a test.
- 2026-10-22: Done. `log_file_handler` in `main.py`, outside the `__main__` block, creates the handler. A test in
  `tests/test_main.py` makes `io.text_encoding` name cp1252 for a file opened without an encoding, and reads a
  line with Korean and Chinese text back from the file in UTF-8, in the format of `FILE_FORMATTER`. Without the
  encoding the line is lost. A patch of `locale.getpreferredencoding` has no effect on `open()`.
