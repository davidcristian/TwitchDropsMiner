# ADR-0001: An independent project

**Status:** Accepted (2026-10-18)

## Context

This repository started as a fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner),
which is released under the MIT License. The original project takes a stance against AI. This project is
developed with AI coding agents that follow [AGENTS.md](../../AGENTS.md). `CLAUDE.md` contains only
`@AGENTS.md`, which imports it, so every agent and every person works by the same rules.

Work made that way cannot be offered to the original project. The repository therefore needs its own license,
its own rules for taking in fixes from the original project, and its own commit history rules.

## Decision

1. **The project is developed on its own, at
   [davidcristian/TwitchDropsMiner](https://github.com/davidcristian/TwitchDropsMiner).** Nothing is sent to
   the original project: no issue and no pull request is opened on DevilXD/TwitchDropsMiner. The reason is the
   original project's stance against AI. The README's Support section and
   [Reporting a problem](../troubleshooting.md#reporting-a-problem) tell users the same.

2. **The project is licensed under the GNU AGPL v3.** `LICENSE` starts with a header that names the project
   and its copyright holder, states that code from the original project remains under the MIT License, and
   points to `LICENSE.MIT`. The full AGPL v3 text follows the header.

3. **The original MIT notice stays, in `LICENSE.MIT`.** The MIT License requires its copyright and permission
   notice to be included in all copies or substantial portions of the software. Code from the original project
   remains under the MIT License, so its notice stays with that code.

4. **The `upstream` remote is read only.** It points to DevilXD/TwitchDropsMiner and is used only to fetch.
   A fix from it comes in by cherry-pick or merge, never by rebasing `master`, because `master` is pushed and a
   rebase rewrites commits that others have already pulled. `master` is never force-pushed.
   [upstream-fixes.md](../runbooks/upstream-fixes.md) gives the steps.

5. **Pull requests are merged with GitHub's rebase merge.** The commits of a pull request go onto `master` in
   a line, with no merge commit. A rebase merge rewrites only the commits of the pull request, not commits
   already on `master`, but it gives each of them a new hash.

6. **New commits use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/); older commits keep
   their style.** Commits taken from upstream and the feature commits made before AGENTS.md existed (such as
   "Implement auto fetch") are not reworded, because rewording a pushed commit means rewriting `master`.
   AGENTS.md's [Commits](../../AGENTS.md#commits) section states the format.

## Consequences

- Two licenses apply to the repository. New code is AGPL v3. Code from the original project is MIT, under the
  notice in `LICENSE.MIT`. The README's License section states both.
- GitHub records the repository as a fork, so `gh` targets the parent repository by default. Each `gh`
  command passes `--repo davidcristian/TwitchDropsMiner`, or the clone sets that repository as the default
  once ([AGENTS.md](../../AGENTS.md#branches-pull-requests-and-remotes)).
- A commit's hash on its pull request branch differs from its hash on `master`, so a hash cited before the
  merge no longer names the commit. Commit messages name a behavior or a decision instead.
- The app does not present itself as DevilXD's work, and it credits the original project in the About box and
  the README. Some names from the original project stay on purpose ([ADR-0007](ADR-0007-kept-identifiers.md)).
- Problems are reported on this repository. The original project's code differs, so a report there does not
  apply to this app.

## Alternatives rejected

- **Offering changes to the original project.** It conflicts with that project's stance against AI.
- **Rebasing `master` onto `upstream/master` to take fixes.** It rewrites pushed history (decision 4).

## Related

- [upstream-fixes.md](../runbooks/upstream-fixes.md): how a fix from DevilXD/TwitchDropsMiner comes in.
- [ADR-0007](ADR-0007-kept-identifiers.md): the names kept from the original project.
- [AGENTS.md](../../AGENTS.md): the rules this project is developed by.
- `LICENSE`, `LICENSE.MIT` and the README's License and Credits sections.
