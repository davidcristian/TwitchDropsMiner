# No test can import `translate` or a module that imports it

**Status:** open
**Area:** translate, tests
**Origin:** Found on 2026-10-20 when a test of `WebsocketPool.start` could not import `websocket.py`
**Verified:** 2026-10-20

In a run from source, `Translator.__init__` writes `English.json` to `LANG_PATH` when `translate` is imported
([translate.md](../../modules/translate.md#why-langenglishjson-is-rewritten-on-every-run-from-source)).
`constants.py` puts `LANG_PATH` in the folder of `sys.argv[0]`. Under `python -m pytest`, as `just check` runs
it, that is the folder of the `pytest` package, which has no `lang` folder, so the import raises:

```
FileNotFoundError: [Errno 2] No such file or directory: '.../site-packages/pytest/lang/English.json.new'
```

`gui`, `inventory`, `twitch` and `websocket` import `translate`, so no test can import them. A fix of their
logic is checked with a stubbed script outside the suite, and nothing runs that check again. `websocket.py`
also imports `utils`, which needs `tkinter` and Pillow ([task 031](031-tests-for-utils-and-settings.md)).

## What a fix involves

Move the write of `English.json` out of the import, into a call that `main()` makes, or skip it when the
`lang` folder does not exist. A test of `WebsocketPool` can then use a fake `Twitch` and a session whose
`ws_connect` raises `aiohttp.ClientConnectionError`, and check that `start()` returns at once and `stop()` ends.
No fix adds a request.

## History

- 2026-10-20: Opened. `WebsocketPool.start` was changed to return without waiting for a connection, and a test
  file that imported `websocket.py` failed with the error above.
