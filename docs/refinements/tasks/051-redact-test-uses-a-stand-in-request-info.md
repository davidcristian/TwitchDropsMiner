# The redact tests use a stand-in for aiohttp's `RequestInfo`

**Status:** open
**Area:** redact, tests
**Origin:** Found on 2026-10-21 when the Validate job started to install aiohttp for the tests
**Verified:** 2026-10-21

`redact` in `redact.py` finds aiohttp's `RequestInfo` by its type name and its four fields, so that it imports
no aiohttp. `tests/test_redact.py` passes a `NamedTuple` with the same name and fields. Both were written for a
Validate job without aiohttp, and that job now installs it ([ADR-0012](../../adr/ADR-0012-check-command.md)).

The stand-in does not change when aiohttp does. When a release renames `RequestInfo` or one of its fields,
`redact` no longer finds it. It then returns a tuple as a plain `tuple` with the secrets hidden, and a value
that is not a tuple unchanged, with its `Proxy-Authorization` header. The tests pass in both cases.

## What a fix involves

`test_redact_hides_the_proxy_password_in_a_request_info` builds an `aiohttp.client_reqrep.RequestInfo` in
place of the stand-in, or in addition to it. `redact` can then check the type with `isinstance`, if importing
aiohttp there is accepted. No fix adds a request.

## History

- 2026-10-21: Opened. The Validate job started to install aiohttp, which removed the reason for the stand-in.
