# `utils.py`

**Purpose.** Holds the helpers that several modules share: reading and writing JSON files, the delays between
retries (`ExponentialBackoff`), running tasks, the `Game` class and small helpers for time, random IDs and the
browser. None of them sends a request to Twitch by itself. The module is over the 300 line cap in AGENTS.md
([refinement task 005](../refinements/tasks/005-modules-over-the-line-cap.md) gives its line count).
`RateLimiter`, which limits the GQL requests, is in [ratelimit.md](ratelimit.md), and `lock_file`, the single
instance lock, in [instancelock.md](instancelock.md).

## Public contract

### JSON files

| Helper | What it does |
| --- | --- |
| `json_save(path, contents, *, sort=False)` | Writes `<name>.new` with an indent of 4, then replaces `path` with it, so a crash during the write leaves the old file whole. When the write or the rename raises `OSError`, the error passes to the caller and `<name>.new` stays |
| `json_load(path, defaults, *, merge=True)` | Reads `<name>.new` first when it exists and deletes it when it is not valid JSON, then reads `path` only when `<name>.new` gave nothing. When neither exists, returns a shallow copy of `defaults`. A `path` that is not valid JSON raises `json.JSONDecodeError` |
| `merge_json(obj, template)` | Called by `json_load` when `merge` is true. Deletes keys that `template` lacks, replaces a value whose type differs from the template's, recurses into dicts and adds missing keys |
| `json_minify(data)` | Returns JSON without spaces, for request and websocket payloads |

`json_save` writes a `datetime` (a naive one counts as UTC), a `set`, an `Enum` (by its value) and a `URL` as
`{"__type": "<class name>", "data": ...}`. Any other type that JSON cannot hold raises `TypeError`. `json_load`
rebuilds these objects through `SERIALIZE_ENV`, which knows `set`, `URL`, `PriorityMode` and `datetime`. It
drops a key whose `__type` is not in `SERIALIZE_ENV`, and the merge then puts the default back.

`json_save` does not delete the `<name>.new` that a failed save leaves, because `json_load` handles both kinds.
A write that the disk cut off leaves a file that is not valid JSON (`json.dump` writes the closing `}` last),
and `json_load` deletes it. A failed rename, such as on Windows while another program has `path` open, leaves a
whole file with the newest contents, and `json_load` reads it in place of `path`.

| Caller | File | Notes |
| --- | --- | --- |
| `settings.py` | `settings.json` | merged with `default_settings`, then `Settings` removes the items that are not strings from its lists and sets ([settings.md](settings.md#loading-settingsjson)) |
| `cache.py` | `cache/mapping.json` | `merge=False`; catches `json.JSONDecodeError` ([cache.md](cache.md)) |
| `translate.py` | `lang/*.json` | merged with `default_translation`. `save_template`, which `main.py` calls in a run from source, saves `lang/English.json` |

`json_minify` is called by `websocket.py` for every message it sends, and by `channel.py` for the spade and GQL
watch payloads, which only uncalled methods read ([channel.md](channel.md#watching)).

### Request pacing

**`ExponentialBackoff(*, base=2, variance=0.1, shift=0, maximum=300)`** is an iterator of delays in seconds:
`base ** steps`, times a random factor between `1 - variance` and `1 + variance` (or the two ends of a tuple),
plus `shift`, and never above `maximum`. `steps` grows only when the delay is at most `maximum`. `reset()` sets
it to 0. A `base` of 1 or less raises `ValueError`. With the defaults the delays are about 1, 2, 4 and 8 seconds.

| Caller | `maximum` | Retries on |
| --- | --- | --- |
| `Twitch.request` | 180 | a status of 500 or above and connection errors |
| `Twitch.gql_request` | 60 | `service error` and `PersistedQueryNotFound` once, after at least 5 seconds; `service timeout`, `request cancelled`, `service unavailable` and `context deadline exceeded` each time |
| `Websocket._backoff_connect` in `websocket.py`, through `ReconnectDelay` | 180 | connection errors and connections that ended within `WS_MIN_UPTIME`; `reset()` after a connection that stayed open that long |

### Tasks

- **`task_wrapper(afunc=None, *, critical=False)`** decorates a coroutine function that runs as a task. It
  ignores `ExitRequest` and `ReloadRequest`, and logs any other exception with its traceback and raises it again.
  With `critical=True` it passes the exception to `Twitch.task_failed` on the `Twitch` object found as the first
  argument or as its `_twitch` attribute, and the task ends without raising it. `Twitch._run` then raises it as
  a fatal error, which restarts the run after the restart delay
  ([twitch.md](twitch.md#restart-after-a-fatal-error)). `Websocket.stop` awaits its task, so a task that
  raised the error would raise it again in `Twitch.shutdown`. The critical tasks are
  `Twitch._watch_loop`, `Twitch._maintenance_task` and `Websocket._handle`. Without `critical` it wraps the
  PubSub handlers `process_stream_state`, `process_stream_update`, `process_drops` and `process_notifications`
  in `twitch.py`, `Websocket.stop` and, in `gui.py`, `Twitch.detect_games` and `HelpTab._invalidate_token`.
- **`start_task(coro)`** starts a task that runs `coro`, keeps it in a module level set until it ends and returns
  it. The event loop keeps only a weak reference to a task, so a task that nothing else references can be
  collected before it ends. `SettingsPanel.rescan_games` and `HelpTab.invalidate_token` in `gui.py`, and
  `Websocket.stop_nowait` and `Websocket._handle_message` in `websocket.py`, start their tasks with it.
- **`AwaitableValue[T]`** is a value that coroutines can wait for: `get()` waits until `set()` is called. It
  also has `has_value()`, `get_with_default(default)` and `clear()`. `Twitch.watching_channel` is one,
  and `Websocket._ws` holds each websocket's connection in one.
- **`chunk(iterable, length)`** yields lists of `length` items; the last list can be shorter. `twitch.py` puts
  20 campaign details, stream checks or available drop checks into one GQL request, and `websocket.py` puts 20
  topics into one `LISTEN` or `UNLISTEN` message.

### `Game`

`Game(data)` is a Twitch game: `id` (an `int`), `name` (`displayName`, or `name` when that is missing) and
`slug` (from the data, or made from the name: lower case, apostrophes removed, and each run of characters other
than letters, digits and `_` turned into one `-`, with no `-` at either end). Two games are equal when their IDs
are. `is_special()` is true for the IDs in `SPECIAL_GAME_IDS` (`509663`, `509672`): for a campaign of that game,
`can_earn` then accepts a channel whatever game it streams, when the campaign's list of allowed channels is
empty or includes it (`inventory.py`, `twitch.py`). `inventory.py`, `channel.py`, `twitch.py` and `gui.py` use
`Game`.

### Other helpers

| Helper | What it does | Caller |
| --- | --- | --- |
| `resource_path(relative_path)` | `constants._resource_path` ([constants.md](constants.md#working-directory-and-paths)) | `main.py`, `gui.py` |
| `set_root_icon(root, image_path)` | Sets the window icon and keeps a reference to the image | `main.py`, `gui.py` |
| `webopen(url)` | Opens `url` in a new browser tab. In a packaged Linux build it restores `LD_LIBRARY_PATH` from `LD_LIBRARY_PATH_ORIG` for the call, because PyInstaller points it at the bundled libraries | `gui.py` |
| `timestamp(string)` | Parses a Twitch UTC time, with or without fractions of a second | `inventory.py`, `twitch.py` |
| `isonow()` | Returns the current UTC time with milliseconds and a `Z` | `channel.py`, in the watch payload that only uncalled methods read |
| `create_nonce(chars, length)`, `CHARS_ASCII`, `CHARS_HEX_LOWER` | Return a random string | `websocket.py` (30 ASCII characters), `twitch.py` (the 16 character hex session ID) |
| `format_traceback(exc, **kwargs)` | Returns the traceback of `exc` and of its cause as a string, as `traceback.format_exception` does. `kwargs` such as `chain=False` go to that function | `websocket.py` |

## Invariants

- A new type stored in a JSON file needs a branch in `_serialize` (every `Enum` already has one) and an entry in
  `SERIALIZE_ENV`. Without the entry, the key is dropped on load and reset to its default. An `IntEnum` is
  written as a plain number and read back as one.
- A task whose result the caller does not keep is started with `start_task`, not with `asyncio.create_task`.
  `ruff check --select RUF006` lists the `asyncio.create_task` calls whose result is not kept.
- `utils` imports `tkinter` and Pillow at the top, so even its JSON helpers need both installed. It imports
  `twitch` only inside `task_wrapper`, which avoids an import cycle.

**Dependencies.** `constants`, `exceptions`, and `twitch` inside `task_wrapper`. Third party: `yarl` and Pillow.
Standard library: `tkinter`, `asyncio`, `json` and others.
