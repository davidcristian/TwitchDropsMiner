# Decision records

An ADR (architecture decision record) states one decision as it stands today: what was decided, why, and what
follows from it. A reader opens it to learn the rule that applies now, so it is short enough to read in one go
and contains nothing that is no longer true.

## The rules

- **One decision per record, at most 250 lines.** A record that needs more is two decisions, or it contains
  history that belongs in git.
- **Edited in place.** When the decision changes, the record is rewritten to state the new decision, and its
  `**Status:**` date moves. Git keeps every earlier version, so nothing is appended: a record never ends with a
  dated list of later changes.
- **Number and filename are permanent.** A record is `ADR-NNNN-slug.md` and is never renumbered, so every link
  to it keeps working. A decision that another one replaces keeps its file, and its status names the record
  that replaced it.
- **Headings are stable.** Other documents link to a section by its anchor, so a heading is renamed only
  together with every link to it.
- **Closing a backlog task is recorded in the task's own file** ([refinements](../refinements/index.md)). It
  changes a record only when it changed the decision that record states.

The prose rules in [AGENTS.md](../../AGENTS.md#prose) apply in full.

## The format

```
# ADR-NNNN: <title>

**Status:** Accepted (<date the decision last changed>)   or   Superseded by ADR-MMMM

## Context
Why a decision was needed, in a few short paragraphs.

## Decision
The numbered decisions, each with its reason in a sentence or two.

## Consequences
What follows: invariants, costs, what the decision rules out.

## Alternatives rejected
Only the ones a future reader would otherwise propose again, one or two lines each.

## Related
Module docs, runbooks, refinement tasks and other ADRs.
```

The list of every record, with a line on what each one decides, is in [docs/index.md](../index.md#decisions).
