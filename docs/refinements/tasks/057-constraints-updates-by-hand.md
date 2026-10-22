# Nothing proposes a new version for `constraints.txt` or checks that it lists every indirect package

**Status:** open
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
