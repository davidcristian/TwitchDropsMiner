# TwitchDropsMiner engineering rules

Every agent and every person working in this repo follows these rules. A change that breaks one of them is **not
done**, even when it works. If a rule here conflicts with a request, follow the rule and say so. This file is the
contract, and the detail lives in `docs/`: the index [docs/index.md](docs/index.md), the map
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), the decisions `docs/adr/`.

## What this is

A desktop app that watches Twitch streams in the background on one account to collect timed drops. It claims each
drop when it is ready and switches channels when a stream goes offline or a campaign with a higher priority starts.
It is Python 3.10+ with `asyncio` and a `tkinter` GUI, built with PyInstaller for Windows and as an AppImage for
Linux (`build.spec`, `appimage/`, `.github/workflows/ci.yml`).

The project started as a fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) and is
developed on its own. It is licensed under the AGPL v3 ([LICENSE](LICENSE)). Code from the original project stays
under the MIT License ([LICENSE.MIT](LICENSE.MIT)). [ADR-0001](docs/adr/ADR-0001-independent-project.md) says why.

## The one hard rule

**Twitch sees no more traffic than a diligent person would cause.** The app runs on the user's own account, and a
burst of requests puts that account at risk.

- Every GQL request goes through `Twitch.gql_request`, where a `RateLimiter` (`utils.py`) allows 5 per second.
  Never send GQL another way.
- A full reload (`State.INVENTORY_FETCH`) can send thousands of GQL operations, batched 20 to a request, when a
  campaign lists many channels. It runs at startup and on every new run (the Invalidate button, a restart after a
  fatal error), once an hour from `_maintenance_task`, after a drop is claimed or its reward notification
  arrives, and from the Reload button. Do not add a timer that runs it more often.
- New periodic work re-enters `State.CHANNELS_CLEANUP`, which moves on to `State.CHANNELS_FETCH` and costs a few
  requests, rather than reloading.
- A change that adds requests states how many per cycle in its commit body.

[ADR-0002](docs/adr/ADR-0002-twitch-traffic-budget.md) gives the request counts this rule rests on.

## Module map

| Module | What it holds |
| --- | --- |
| `main.py` | Entry point: arguments, logging, the single instance lock, the report of a fatal error in the Output box, the exit code |
| `twitch.py` | `Twitch`: login, HTTP and GQL requests, the `State` machine in `_run`, choosing and watching channels |
| `inventory.py` | `DropsCampaign` and `TimedDrop`: campaign data, drop progress, claiming |
| `channel.py` | `Channel` and `Stream`: stream state and online checks |
| `websocket.py` | The PubSub websocket pool and its topics |
| `gui.py` | The whole GUI. `python gui.py` opens it with mock data and no login; it downloads only the mock's images |
| `settings.py` | `settings.json`: the `SettingsFile` type, its defaults, loading and saving |
| `constants.py` | Paths, intervals, `State`, `PriorityMode`, and the GQL queries with their hashes |
| `translate.py` | The `Translation` types and the English strings. Other languages are in `lang/` |
| `utils.py` | JSON helpers, `RateLimiter`, `ExponentialBackoff` and task helpers |
| `cache.py` | The image cache for game and drop artwork |
| `registry.py` | Windows registry access, used for starting with Windows |
| `exceptions.py` | `MinerException` and its subclasses, including `ExitRequest` and `ReloadRequest` |
| `redact.py` | `redact`, which hides the login token and other secrets in a value before a log call prints it |
| `reconnect.py` | `ReconnectDelay`, the wait of a PubSub websocket before each reconnect |
| `gqldata.py` | Reads GQL responses and leaves out the fields that a server error set to null |
| `imagedata.py` | `decode_image`, which decodes a whole image download for `cache.py` or returns None for broken data |
| `version.py` | `__version__`, to which CI appends the commit hash. Its doc is part of `docs/modules/constants.md` |
| `gamelib/` | Finds installed games and matches names ignoring case and accents. `steam.py` and `epic.py` read the Steam, Epic, Legendary and Heroic install indexes, `scan.py` runs both, `matching.py` pairs installed games with Twitch games, `patterns.py` matches list entries with `*` and `?`, `common.py` holds the shared types. `__init__.py` re-exports the public names |
| `docs/` | Listed in `docs/index.md`: `ARCHITECTURE.md`, the decisions (`adr/`), one contract doc per module (`modules/`), procedures (`runbooks/`), the deferred work (`refinements/`), and two pages for users, `building.md` (running from source, building, packaging) and `troubleshooting.md` (common problems, command line flags) |

**At most 300 lines per module**, which `scripts/linecap.py` checks. It names the eight inherited modules over the
limit as exceptions until they are split ([task 005](docs/refinements/tasks/005-modules-over-the-line-cap.md)), and
an exception fails once its module is under the limit. Do not add a new responsibility to a module over the limit:
put it in a new module and call it from there.

## Code rules

New code follows these ([ADR-0014](docs/adr/ADR-0014-code-rules.md)), and so does code that a change rewrites.

- **Logic apart from I/O.** New logic that calls Twitch, the disk or the OS receives that call as an argument (a
  `Protocol` or a function), so a test passes a fake. The code that makes the real call holds no decisions.
- **Platform differences in one place.** New Windows, Linux or macOS behavior goes in one function per concern,
  which the rest of the code calls, rather than in an inline `sys.platform` check.
- **Types.** Public functions are fully typed, and `Any` is used only where any value is accepted. Errors are
  specific exception classes, `MinerException` subclasses for the app's own. No bare `except:`, and
  `except Exception` only where a task must keep running, which then logs the error.

## Recipes

**A new setting** touches four places, and missing the third is silent:

1. `SettingsFile`, `default_settings` and the attribute list on `Settings`, in `settings.py`.
2. The widget in `SettingsPanel`, in `gui.py`.
3. The `settings=SimpleNamespace(...)` mock under `if __name__ == "__main__":` at the end of `gui.py`. Without it
   `python gui.py` fails with an `AttributeError`, and nothing else reports it.
4. The key table in [docs/modules/settings.md](docs/modules/settings.md).

**A string the user sees:**

1. Add a key to the matching `TypedDict` and to `default_translation`, both in `translate.py`.
2. Read it with `_("section", "key")`. Never hard-code text that the GUI or the console shows.
3. Leave `lang/English.json` alone: it is gitignored, and every run from source rewrites it.
4. Other languages need no edit, because a missing key falls back to English.

**An edit to `gui.py`:** many of its classes share identical lines, such as their `__init__` signature. Before a
search and replace edit, check that the search text occurs once in the file: a replacement on a repeated line puts
the code in the wrong class, which shows only at runtime.

**A new module** gets a row in the module map and a doc in `docs/modules/`. When it needs neither Twitch nor a
display, add it to `source` under `[tool.coverage.run]` in `pyproject.toml`. A new package (a folder of modules,
such as `gamelib/`) also goes in the `cp` and `compileall` lines of `appimage/AppImageBuilder.yml`, which take only
the top-level `*.py` files; without it the AppImage fails at startup with a `ModuleNotFoundError`.

## What every change must pass

**`just check` is the single command, and it must pass.** The pre-commit hook and the Validate job in CI run it.
[docs/building.md](docs/building.md#run-the-checks) sets it up, and [ADR-0012](docs/adr/ADR-0012-check-command.md)
gives the reasons. In order, it runs `syntaxcheck.py` (Python 3.10 syntax), `langcheck.py` (the JSON and the format
fields of `lang/*.json`), ruff (the rules in `pyproject.toml`), `linecap.py` (the line limits), `dashcheck.py` and
`prosecheck.py` (the Prose rules a script can read), `docscheck.py` (the links between docs, line numbers, the two
indexes and the record formats), `rostercheck.py` (the module map, the module docs, the settings keys, the `gui.py`
mock and this list), and pytest over `tests/`, which fails below 80% branch coverage of the modules `pyproject.toml`
lists. No check finds 3.11+ names such as `typing.Self` and `tomllib`, which fail only on import: avoid them.

The rest is checked by hand, and the report of a change shows the output of each:

1. **Tests assert behavior** ([ADR-0013](docs/adr/ADR-0013-test-standard.md)). A bug fix adds a test that fails
   without it. A module that needs neither Twitch nor a display tests each public function with its error and edge
   cases, with fakes, not mocks, and no test only to reach a line. A known defect is a strict `xfail` test that
   names its task file.
2. A GUI change is run in `python gui.py` or `python main.py`. When the GUI cannot start, the GUI part is reported
   as unverified and the change is not done. [The headless runbook](docs/runbooks/gui-preview-headless.md) runs it
   on Linux without a display.
3. Logic that needs Twitch is called with stubbed inputs, and the inputs and results are shown.
4. No new dependency unless the standard library cannot do the job. Every build installs `requirements.txt`; the
   tools `just check` runs are in `requirements-dev.txt`, which no build installs.
5. No secrets in the repo or in logs. `cookies.jar` holds the login session; it, `settings.json`, `log.txt` and
   `dump.dat` are gitignored and are never committed or pasted. A log call that prints a request, a response or a
   websocket message passes it through `redact` in `redact.py` ([ADR-0011](docs/adr/ADR-0011-secrets-in-logs.md)).

## Prose

Write comments, docstrings, docs and commit messages in plain English that a new reader understands at once.

- **Comments.** Code has no comment unless one is strictly necessary: why a workaround exists, a constraint the
  code cannot show, a Twitch behavior the code depends on, or a directive a tool reads (`# noqa`). Delete one that
  repeats the code, tells history ("was X, now Y"), cites an ADR for background, or says what a better name would
  say. A comment is one or two lines, three at most.
- **Docstrings** are one line saying what the module, class or function does; delete one that only repeats the name.
  Tests have none: the test name says what it checks. A second or third line only explains an argument or return
  value that its name and type do not, and never more: design reasons go in an ADR or a module doc, history in git.
- **Docs** are short and written for a reader who has never seen this repo: what a thing is and does, then why,
  when the why is not obvious. Keep facts, numbers, commands, file paths and decisions, and name code by its
  function or class, never by a line number. Cut the story of how the code got here, repeated explanations (link
  to the one place instead) and hedging. A markdown file is at most 250 lines: a longer one says two things.
- **Plain words.** Short sentences, one idea each, subject first, with the literal verb: "checks", "fails",
  "returns", "stores", "sends", "is set to". Code does not know, notice, want, refuse, believe, agree, argue,
  answer, promise or own anything, so say what it does: a server returns a response. Define a technical term
  once, where it first appears. No metaphors, idioms, wordplay or invented terms. Anything in backticks is exempt.
- **No dash as punctuation.** No em dash, en dash or spaced `--`. Restructure the sentence instead.

**Banned words.** The words in the left column may not appear in prose, in any capitalization, even split by a
line break. `prosecheck.py` reads this table for every text file except `LICENSE*` and `lang/`, and
`commitlint.py` for commit messages; neither reads backticks, link targets or URLs. The table is a minimum:
rewrite any other figurative word the same way.

| Do not write | Write instead |
| --- | --- |
| load-bearing | required, essential |
| gate, gates, gated, gating, ungated | check, checked, must pass, enforced by |
| pin, pins, pinned, pinning | fix, lock, set exactly, assert |
| spell, spells, spelled, spelling, spellings, respell | write, name, define, form |
| carry, carries, carried, carrying | contain, include, have, keep, pass |
| land, lands, landed, landing | commit, merge, add, end up |
| seam, seams | boundary, interface |
| arm, arms, armed, arming | variant, condition, branch, set, enable |
| sitting, sittings | run, measurement session |
| sweep, sweeps | review, pass |
| heal, heals, healed, healing | fix, repair |
| bite, bites | name the event that makes it matter |
| ride, rides, riding | is sent with, goes with |
| standing | current, permanent, ongoing |
| in force | current, in effect |
| needle, needles | search text |
| knob, knobs | setting |
| lever, levers | setting, option |
| honest, honestly | accurate, correct, real |
| verdict, verdicts | result |
| re-derive, re-derives, re-derived, re-deriving, rederive | recompute, check again |
| earn, earns, earned | say why it is justified |
| backstop, tripwire, ratchet, footgun, chokepoint | describe the mechanism |
| robust, seamless, seamlessly, comprehensive, crucial, crucially, critically, fundamentally | state the specific fact |
| leverage, leverages, delve, utilize, worth noting | use, look at, (state the fact) |
| under the hood, boils down, low-hanging, rabbit hole, north star, belt and braces, silver bullet | say it literally |

## Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), checked by two commit-msg hooks:
conventional-pre-commit for the type and format, `scripts/commitlint.py` for the rest of these rules, the banned
words and the dash rule included. No script checks the imperative mood. Older commits, including those taken from
upstream, keep their original style and are not reworded.

- **The subject says what changed; the body says why it was needed.** A subject starts with a verb of change
  (`add`, `fix`, `remove`, `split`, `rename`), names what changed rather than a relation between two files, and
  reads correctly to someone who has not seen the diff. The body states the problem, then what the change does
  about it, in two or three plain sentences. Write no body when the subject says everything. Reasoning belongs in
  `docs/`, and a message that needs it points there.
- Format: `type(scope)?: subject`, imperative mood, lowercase subject, no trailing period, first line at most 72
  characters. The body is at most 50 words and wraps at 72, except a line of one word. A paste, which is a line in
  a code fence or after a `$ ` prompt, is exempt from the wrap, the word count and the dash rule, and from nothing
  else. A fence that nothing closes fails.
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `revert`. A breaking change
  adds `!` after the type or scope and a `BREAKING CHANGE:` footer. A scope is optional, only for a change inside
  one module or area: the module name without `.py` (`gui`, `twitch`), `lang` or `ci`, never the type (`ci(ci)`).
- **No volatile references.** Never cite a commit hash, an issue or PR number, an ADR or backlog task number, or
  any other numbered pointer into a document (`check 3`), in a paste too. Name the behavior or the decision
  instead. Code paths, package names and environment variables are welcome.
- One logical change per commit, and every commit passes `just check`.

## Branches, pull requests and remotes

- Work happens on a `feat/...`, `fix/...`, `docs/...` or `chore/...` branch and reaches `master` through one pull
  request per logical concern on [davidcristian/TwitchDropsMiner](https://github.com/davidcristian/TwitchDropsMiner).
- Never force-push `master`. Rewriting a branch nobody else has pulled is fine.
- DevilXD/TwitchDropsMiner (the `upstream` remote) is read only for this project: fetch from it, but never open an
  issue or a pull request there. Its fixes come in by cherry-pick or merge, never by rebasing `master`
  ([docs/runbooks/upstream-fixes.md](docs/runbooks/upstream-fixes.md)).
- GitHub records this repo as a fork, so `gh` targets the parent repo by default: pass
  `--repo davidcristian/TwitchDropsMiner`, or run `gh repo set-default` once per clone.

## Working agreement

- **Claims come with evidence.** Never report a check as passing without having run it in this session; show the
  command and its output. Label an unverified statement as an assumption.
- **Prove a check can fail.** After writing or changing a check, break the thing it checks and watch it fail
  before trusting it. The table of each break and its result goes in the body of the commit that makes the
  check, inside a code fence, and names the test suite its counts are over.
- **The agent runs what it can reach**: the tests, the GUI without a display, Twitch code against stubs. Only a
  real Twitch login, a real drop claim and Windows or macOS behavior are left to the maintainer, and the report
  names each. Work the agent can do now is done now, not deferred.
- **Names are chosen with care the first time.** A `settings.json` key or a file the app writes cannot change once
  users' files depend on it ([ADR-0007](docs/adr/ADR-0007-kept-identifiers.md)): propose it with an alternative.
- **Read before you write.** Open the file and its call sites before editing. Never edit from memory of its
  contents, and never invent an API: check the signature.
- **Report faithfully.** Report a failing check with its output and name every step you skipped. Report a task as
  done only when it is: an inaccurate "done" costs more to undo than an accurate "not yet".
- **Stop when surprised.** When output contradicts your model of the system, work it out again from the evidence.
  Do not match it to the nearest familiar failure and push through.
- **Docs change with behavior**, in the same commit. What the user sees or does: `README.md` and its page in
  `docs/`. A build script or CI: `docs/building.md`. A module's contract or invariants: its doc in `docs/modules/`.
  A new state, event, GQL operation or background task: `docs/ARCHITECTURE.md`. A procedure: its runbook in
  `docs/runbooks/`. The module map, a recipe or a check: this file.
- **Decisions are written down.** A non-obvious choice becomes an ADR in the format in
  [docs/adr/README.md](docs/adr/README.md), with a line in `docs/index.md`; it states the decision that applies
  today and is edited in place when that changes. When a request leaves a choice open, record your reading of it
  as an ADR, continue, and name the riskiest assumption in your summary.
- **Deferred work is written down.** Work left for later, and a gap found and not fixed, becomes a task file in
  `docs/refinements/tasks/`, in the format in [docs/refinements/index.md](docs/refinements/index.md). A deferral
  without a record is a lost decision. A task's state is written on its `**Status:**` line and nowhere else.
- Keep this file and all docs short and full of pointers; context bloat is a defect.
