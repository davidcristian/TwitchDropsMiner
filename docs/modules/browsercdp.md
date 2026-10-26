# `browsercdp.py`

**Purpose.** The real `BrowserConnection` for [browser.md](browser.md). It starts a Chromium-based browser on a
loopback debugging port with a throwaway profile, connects to its first page over the Chrome DevTools Protocol,
and turns the page's network events into the `NetworkEvent`s the engine reads. On Linux a refresh runs the browser
under a throwaway virtual display with `xvfb-run`, so a real (not headless) browser is invisible.

## Public contract

- `launch(browser_path, options)` is an async context manager that starts the browser with `browser.launch_args`,
  waits for its debugging port, connects to its first page, enables the network domain, and yields a
  `CdpConnection`. On exit it stops the browser and every process it started and removes the profile. With
  `options.xvfb` it runs the browser under `xvfb-run` and raises `RuntimeError` when `xvfb-run` is not installed.
- `CdpConnection` implements `browser.BrowserConnection`:
  - `set_cookie`, `navigate` and `cookies` send `Network.setCookie`, `Page.navigate` and `Network.getAllCookies`.
  - `next_event(timeout)` returns the next request or response the page made, or `None` after `timeout` seconds. A
    `Network.requestWillBeSent` becomes a request event with its URL and headers; a `Network.loadingFinished`
    becomes a response event with the URL from the matching `Network.responseReceived`.
  - `response_body(request_id)` returns the body of a response, or `None` when it cannot be read.
- `free_port()` returns a loopback port that is free when it is called.

## Invariants

- The browser runs with a throwaway profile that `launch` removes when it exits.
- On a POSIX system the browser starts in its own session, so stopping it stops `xvfb-run` and every child.
- The module holds no decisions: `browser.py` chooses the arguments, the page and when a capture is complete.

**Dependencies.** Repo modules: `browser`. Otherwise `aiohttp` and the standard library (`asyncio`, `socket`,
`signal`, `tempfile`, `contextlib`).
