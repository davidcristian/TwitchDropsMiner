# Nothing proposes a new version for `constraints.txt` or checks that it lists every indirect package

**Status:** done 2026-10-22
**Area:** build, ci
**Origin:** Found on 2026-10-22 while the update rule for `constraints.txt` was written
**Verified:** 2026-10-22

`constraints.txt` is updated by hand, once a month and for each security release
([ADR-0016](../../adr/ADR-0016-exact-dependency-versions.md)), with the commands in
[runbooks/dependency-versions.md](../../runbooks/dependency-versions.md). Two parts of that work have no tool:

- **No pull request proposes a new version.** `.github/dependabot.yml` updates only the actions. Whether
  Dependabot's `pip` updates read a file named `constraints.txt` was not checked, because that needs a run on
  GitHub. Such an entry would also update `requirements-dev.txt`, whose `rust-just` version changes only together
  with the three hashes in `ci.yml`. Dependabot's commit bodies list links and hashes, which the commit rules do
  not allow ([building.md](../../building.md#release-builds)).
- **No job fails on an indirect package that the file lacks.** `tests/test_constraints.py` checks the packages
  that the builds and `requirements.txt` name. When a new version adds a dependency, each build installs that
  dependency at its newest release, and only the runbook's `compare.py` lists it.

## What a fix involves

1. Add a `package-ecosystem: pip` entry for `/` on a branch, and read the pull requests that Dependabot opens:
   whether they change `constraints.txt`, and whether they keep the two week wait.
2. Add a step after the installs of each PyInstaller build job that compares `pip freeze --all` with
   `constraints.txt`, and fails on a package that the file lacks or sets to another version. The AppImage job
   installs into the system Python of Ubuntu, whose list includes the system's own packages, so it needs another
   check. The new check is shown to fail before it is trusted ([AGENTS.md](../../../AGENTS.md#working-agreement)).

None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the update rule for `constraints.txt` was written.
- 2026-10-22: Each build job runs `scripts/installcheck.py` after its installs, which fails on a package that
  `constraints.txt` lacks or sets to another version. The AppImage job checks the user's site folder and the
  AppDir, so the Debian packages of Ubuntu's Python stay out.
- 2026-10-22: Step 1 of the runbook saves the files of the kept lines into a folder that `--find-links` names,
  so that a kept line newer than two weeks, such as aiohttp 3.14.5, resolves with `--uploaded-prior-to P14D`.
- 2026-10-22: Closed. dependabot-core reads `constraints.txt` as a requirements file, so a `pip` entry in
  `.github/dependabot.yml` opens one pull request a month with a cooldown of 14 days, which security updates
  skip, and leaves out rust-just and the limits that other packages set. `requirements-dev.txt` names the file
  with `-c`, so that the dependency graph, from which the security alerts come, reads it
  ([ADR-0016](../../adr/ADR-0016-exact-dependency-versions.md)). Only GitHub can show the first pull request of
  Dependabot and the packages of `constraints.txt` in the dependency graph.
- 2026-10-22: Dependabot chooses releases for Python 3.14, so `ignore` leaves out the releases that drop Python
  3.10, which the Validate job and the AppImage use: Pillow 13 and pre-commit 4.7.
