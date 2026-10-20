# A `WebsocketTopic` equals its text but has a different hash

**Status:** open
**Area:** constants, websocket
**Origin:** Found on 2026-10-20 while writing the tests of `constants.py`
**Verified:** 2026-10-20

`WebsocketTopic.__eq__` in `constants.py` returns true for a string with the same text, such as
`"broadcast-settings-update.7"`. `WebsocketTopic.__hash__` hashes the class name together with the text, so the
topic and the string have different hashes. Python requires objects that compare equal to have equal hashes,
and a set or dict lookup by the text misses the topic: `"broadcast-settings-update.7" in {topic}` is false. The
strict `xfail` test `test_a_websocket_topic_is_found_in_a_set_by_its_text` in `tests/test_constants.py` asserts
the correct result.

No code is affected today. `Websocket.topics` is a dict keyed by the text, and each set that `websocket.py`
builds holds either topics or strings, never both. Nothing compares a topic with a string.

## What a fix involves

Return `hash(self._id)` from `__hash__`, or remove the string branch of `__eq__`. Either fix adds no request.

## History

- 2026-10-20: Opened. A test of `WebsocketTopic` looked up a topic by its text in a set.
