# TwitchDropsMiner engineering rules

Every agent and every person working in this repo follows these rules. A change that breaks one of them is **not
done**, even when it works. If a rule here conflicts with a request, follow the rule and say so.

## What this is

A desktop app that watches Twitch streams in the background on one account to collect timed drops. It claims each
drop when it is ready and switches channels when a stream goes offline or a campaign with a higher priority starts.
It is Python 3.10+ with `asyncio` and a `tkinter` GUI, built with PyInstaller for Windows and as an AppImage for
Linux (`build.spec`, `appimage/`, `.github/workflows/ci.yml`).

The project started as a fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) and is
developed on its own. It is licensed under the AGPL v3 ([LICENSE](LICENSE)). Code from the original project stays
under the MIT License ([LICENSE.MIT](LICENSE.MIT)).

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
| `gamelib/` | Finds installed games and matches names ignoring case and accents. `steam.py` and `epic.py` read the Steam, Epic, Legendary and Heroic install indexes, `scan.py` runs both, `matching.py` pairs installed games with Twitch games, `patterns.py` matches list entries with `*` and `?`, `common.py` holds the shared types. `__init__.py` re-exports the public names |
| `docs/` | Docs for users: `building.md` (running from source, building, packaging) and `troubleshooting.md` (common problems, command line flags) |

**Soft cap: 300 lines per module.** Most inherited modules are over it, and `gui.py` and `twitch.py` are several
times over. Do not add a new responsibility to a module that is over the cap: put it in a new module and call it
from there. Keep I/O at the edges of that module, so its logic can be called without Twitch or a display.

## Recipes

**A new setting** touches three places, and missing the third is silent:

1. `SettingsFile`, `default_settings` and the attribute list on `Settings`, in `settings.py`.
2. The widget in `SettingsPanel`, in `gui.py`.
3. The `settings=SimpleNamespace(...)` mock under `if __name__ == "__main__":` at the end of `gui.py`. Without it
   `python gui.py` fails with an `AttributeError`, and nothing else reports it.

**A string the user sees:**

1. Add a key to the matching `TypedDict` and to `default_translation`, both in `translate.py`.
2. Read it with `_("section", "key")`. Never hard-code text that the GUI or the console shows.
3. Leave `lang/English.json` alone. It is gitignored, and every run from source rewrites it from
   `default_translation`.
4. Other languages need no edit, because a missing key falls back to English. An edit to `lang/*.json` must stay
   valid JSON, which CI checks.

**An edit to `gui.py`:** many of its classes share identical lines, such as the
`__init__(self, manager: GUIManager, master: ttk.Widget)` signature. Before a search and replace edit, check that
the search text occurs once in the file. A replacement on a repeated line puts the code in the wrong class, and
the mistake shows only at runtime.

**A new package** (a folder of modules, such as `gamelib/`): the `cp` and `compileall` lines in
`appimage/AppImageBuilder.yml` take only the top-level `*.py` files, so add the folder to both, and to the
`py_compile` check below. Without it the AppImage fails at startup with a `ModuleNotFoundError`. PyInstaller
follows the imports, so `build.spec` needs no change.

## What every change must pass

There is no test suite, linter or single check command yet. Until there is, run each of these and report it with
its command and output. The commands use `python`; on Linux outside the `env/` virtual environment that
`setup_env.sh` creates, use `python3`.

1. `python -m py_compile *.py gamelib/*.py` succeeds. Code must run on Python 3.10, the version CI builds with,
   so no `except*`, `typing.Self`, `tomllib` or other 3.11+ features.
2. `for f in lang/*.json; do python -m json.tool "$f" > /dev/null || echo "$f"; done` prints nothing. CI's
   Validate job runs the same check.
3. A GUI change is run in `python gui.py` or the full app (`python main.py`). When the GUI cannot start (no
   `tkinter`, or no display), the GUI part is reported as unverified, and the change is not done.
4. Logic that needs neither Twitch nor a display is checked by calling it with real inputs, and the inputs and
   results are shown. A pytest suite is welcome and should start with such logic.
5. No new dependency unless the standard library cannot do the job. `requirements.txt` is installed into every
   build.
6. No secrets in the repo or in logs. `cookies.jar` holds the login session; it, `settings.json`, `log.txt` and
   `dump.dat` are gitignored and are never committed or pasted.

## Prose

Write comments, docstrings, docs and commit messages in plain English that a new reader understands on the first
read.

- **Comments** say why: a workaround, a constraint the code cannot show, or a Twitch behavior the code depends on.
  Delete a comment that repeats the code or tells history ("was X, now Y"). A comment is one or two lines, three
  at most.
- **Docstrings** are one line saying what the module, class or function does. Add a second or third line only when
  an argument or return value is not obvious from its name and type.
- **Docs** are short and written for a reader who has never seen this repo: what a thing is and does, then why,
  when the why is not obvious. Keep facts, numbers, commands, file paths and decisions. Cut the story of how the
  code got here, repeated explanations (link to the one place instead) and hedging.
- **Plain words.** Short sentences, one idea each, subject first, with the literal verb: "checks", "fails",
  "returns", "stores", "sends", "is set to". Code does not know, notice, want, refuse, believe or own anything,
  so say what it does. Define a technical term once, where it first appears. No metaphors, idioms or wordplay.
  Anything in backticks is exempt.
- **No dash as punctuation.** No em dash, en dash or spaced `--`. Restructure the sentence instead.

**Banned words.** The words in the left column may not appear in prose or in commit messages, in any
capitalization. No script checks this here, so check it by hand. The table is a minimum: rewrite any other
figurative word the same way.

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

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Older commits, including those taken
from upstream, keep their original style and are not reworded.

- **The subject says what changed; the body says why it was needed.** A subject starts with a verb of change
  (`add`, `fix`, `remove`, `split`, `rename`) and reads correctly to someone who has not seen the diff. The body
  states the problem, then what the change does about it. Write no body when the subject says everything.
- Format: `type(scope)?: subject`, imperative mood, lowercase subject, no trailing period, subject at most 72
  characters. The body is at most 50 words and wraps at 72.
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `revert`. A breaking change
  adds `!` after the type or scope and a `BREAKING CHANGE:` footer. A scope is optional and used only when the
  change stays inside one module or area: the module name without `.py` (`gui`, `twitch`), `lang` or `ci`.
- **No volatile references.** Never cite a commit hash, an issue or PR number, or a numbered pointer into a
  document that changes. Name the behavior or the decision instead.
- The banned words and the dash rule apply to commit messages.
- One logical change per commit, and every commit passes the checks above.

## Branches, pull requests and remotes

- Work happens on a branch named `feat/...`, `fix/...`, `docs/...` or `chore/...` and reaches `master` through a
  pull request on [davidcristian/TwitchDropsMiner](https://github.com/davidcristian/TwitchDropsMiner). One
  logical concern per pull request.
- Never force-push `master`. Rewriting a branch nobody else has pulled is fine.
- DevilXD/TwitchDropsMiner (the `upstream` remote) is read only for this project: fetch from it, but never open an
  issue or a pull request there. Its fixes come in by cherry-pick or merge, never by rebasing `master`.
- GitHub records this repo as a fork, so `gh` targets the parent repo by default. Pass
  `--repo davidcristian/TwitchDropsMiner`, or run `gh repo set-default davidcristian/TwitchDropsMiner` once per
  clone.

## Working agreement

- **Claims come with evidence.** Never report a check as passing without having run it in this session; show the
  command and its output. Label an unverified statement as an assumption.
- **Prove a check can fail.** After writing or changing a check, break the thing it checks and watch it fail
  before trusting it.
- **Read before you write.** Open the file and its call sites before editing. Never edit from memory of its
  contents, and never invent an API: check the signature.
- **Report faithfully.** Report a failing check with its output and name every step you skipped. Report a task as
  done only when it is: an inaccurate "done" costs more to undo than an accurate "not yet".
- **Stop when surprised.** When output contradicts your model of the system, work it out again from the evidence.
  Do not match it to the nearest familiar failure and push through.
- **Docs change with behavior.** A change to what the user sees or does updates `README.md` and the matching page
  in `docs/` in the same commit. A change to a build script or to CI updates `docs/building.md`. A change to a
  module, a recipe or a check updates this file.
- Keep this file and all docs short and full of pointers; context bloat is a defect.
