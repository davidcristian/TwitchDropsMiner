# ADR-0008: The docs layout

**Status:** Accepted (2026-10-18)

## Context

Before this layout, the committed docs were `README.md`, `AGENTS.md`, the `manual.txt` that every release
includes, and two pages for users, `docs/building.md` and `docs/troubleshooting.md`. They had no place for the
reason behind a decision, for what a module's callers depend on, or for a known gap left for later.

On 2026-10-18 the maintainer asked that the docs follow the practices of Cortex, another of the maintainer's
repos. In Cortex, `AGENTS.md` is the contract and `docs/` holds the detail: a start page, an architecture map,
decision records, one contract doc per module, runbooks, a backlog with one file per task, a folder of
measurements, a folder of work that waits on special hardware, and a roadmap of slices. `just check` runs
scripts that check its docs: the line limit, the banned words, the dashes and the backlog index. This repo has
no check command yet ([task 004](../refinements/tasks/004-single-check-command.md)). This record states which
Cortex practices this repo adopts, which it does not, and why.

## Decision

1. **`AGENTS.md` is the contract, and the detail lives in `docs/`.** AGENTS.md holds the rules that every
   change follows and points to the doc with the detail, as its first paragraph says. `CLAUDE.md` contains
   only `@AGENTS.md`, so every agent session loads the whole file, and AGENTS.md calls context bloat a defect.

2. **[docs/index.md](../index.md) is the start page.** It links the pages for users, the map, the runbooks and
   the backlog, and its tables list every ADR and every module doc with a line on what each one covers. A new
   ADR or module doc gets its row in the same commit.

3. **[docs/ARCHITECTURE.md](../ARCHITECTURE.md) is the map:** the objects, the state machine, the path from
   login to a claimed drop, the Twitch requests, the background tasks, the platform code and the repo map.

4. **An ADR states the decision that applies today.** A record in `docs/adr/` is edited in place when its
   decision changes, and its `**Status:**` date moves. Git keeps the earlier versions. Its number and filename
   never change, so every link to it keeps working. [README.md](README.md) gives the rules and the format,
   which follow Cortex's without the readings records.

5. **Every module in the [module map](../../AGENTS.md#module-map) has a contract doc in `docs/modules/`.**
   Each gives the purpose, the public contract, the invariants and the dependencies. The `gamelib/` package
   has one doc, and [constants.md](../modules/constants.md) also covers `version.py`. `gui.py` and `twitch.py`
   are several times over the 300 line cap
   ([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)), so a contract doc lets a reader check
   a change against what the callers depend on without reading the module.

6. **Procedures are runbooks in `docs/runbooks/`,** one file per procedure, each with its steps, its commands
   and a check of the result. The three today cover a changed GQL operation, a fix from upstream and the GUI
   preview without a display.

7. **Deferred work is one file per task in `docs/refinements/tasks/`.** A task's state is written only on its
   `**Status:**` line, and a closed task keeps its file as the record of what the deferral became. The list in
   [refinements/index.md](../refinements/index.md) gives each task's title and area and no status. So the list
   needs no edit when a task changes state, and it cannot disagree with a task file about a state.

8. **A markdown file is at most 250 lines, and the prose rules apply to every doc.** The
   [Prose](../../AGENTS.md#prose) section of AGENTS.md sets both. A file that needs more lines says two things
   and is split.

9. **Four Cortex practices are not adopted:**
   - **`docs/readings/`.** Cortex keeps the measurements its decisions rest on there, each with its date and
     method. This repo has no measurements. The figures in its ADRs are counted from the code, such as the
     request counts in ADR-0002 and ADR-0003.
   - **`docs/host/`.** Cortex keeps work there that is written and waits on hardware its dev machine lacks. No
     work here waits on special hardware. Work that waits on a run with a Twitch login has no record yet.
   - **A roadmap of slices.** Cortex's `ROADMAP.md` orders its planned vertical slices. No planned slices
     exist here.
   - **A generated and checked backlog index.** Cortex writes its index from the task files with
     `just backlog`, and a check fails when the index is out of date. This repo has no check command yet
     (task 004), so the list is written by hand. Because it gives no status, it changes only when a task is
     added.

10. **No empty folders.** Cortex's AGENTS.md says "No scaffolding of empty layers" about code, and this repo
    applies the same rule to `docs/`: it has no empty `docs/readings/` or `docs/host/`. A folder is added with
    its first file, and not before.

## Consequences

- A change updates the doc that describes it, in the same commit. The
  [working agreement](../../AGENTS.md#working-agreement) in AGENTS.md names the doc for each kind of change:
  `README.md` and the page for users, `docs/building.md`, the module doc, `ARCHITECTURE.md`, the runbook, or
  AGENTS.md itself.
- A new decision becomes an ADR with the next free number and a row in `docs/index.md`. A deferral becomes a
  task file with the next free number and a row in the refinements list. Both rows go in the commit that adds
  the file.
- A commit message cites no ADR or task number, as the [Commits](../../AGENTS.md#commits) section says. It
  names the decision or the behavior instead.
- Nothing in the repo checks the line limit, the prose rules or that the links between docs resolve. They are
  checked by hand. Task 004 proposes a script for the line limit, the banned words, the dash rule and the
  links.
- The docs for users stay `README.md`, `manual.txt`, `docs/building.md` and `docs/troubleshooting.md`. The rest
  of `docs/` is for people who change the code.

## Alternatives rejected

- **The flatter layout of the maintainer's HeadStart repo.** Its `docs/README.md` maps single files, among
  them one `runbook.md` and a `roadmap.md` whose lists hold the open work, so every change of state edits one
  shared file. It sets no line limit on docs, and 6 of its 16 module docs are over 250 lines.

## Related

- [README.md](README.md): the rules and the format of a decision record.
- [refinements/index.md](../refinements/index.md): the task format and how to work the backlog.
- [docs/index.md](../index.md) and [ARCHITECTURE.md](../ARCHITECTURE.md).
- [AGENTS.md](../../AGENTS.md): the [working agreement](../../AGENTS.md#working-agreement) and the
  [Prose](../../AGENTS.md#prose) rules.
- [004](../refinements/tasks/004-single-check-command.md): the check command that would check the line limit
  and the prose rules. [005](../refinements/tasks/005-modules-over-the-line-cap.md): the modules over the line
  cap.
