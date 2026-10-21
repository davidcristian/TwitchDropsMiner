# The `just` binary and a commit message hook are not checked against a hash

**Status:** open
**Area:** repo checks, ci
**Origin:** Found on 2026-10-21 while the dependency versions were listed: the metadata of `rust-just`
1.58.0 in `env/` names `github.com/gnpaone/rust-just` as its repository
**Verified:** 2026-10-21

Two tools that run on every commit can change under the name the repo gives them
([ADR-0012](../../adr/ADR-0012-check-command.md#consequences)):

- `requirements-dev.txt` installs `rust-just==1.58.0` from PyPI. The package is a build of `just` by another
  person, from `github.com/gnpaone/rust-just`, not a release of the `just` project. Its `just` binary runs
  `just check` before each commit and in the Validate job. pip checks no hash, so a file replaced on PyPI under
  the same version is installed by the next `pip install`.
- `.pre-commit-config.yaml` names the `conventional-pre-commit` hook by the tag `v4.4.0`. The hook runs on every
  commit message. A machine that installs the hooks after the tag moves runs the code the tag then names.

## What a fix involves

1. **The hook.** Write the commit that the tag names in `rev`, with the tag in a comment
   (`rev: <commit>  # frozen: v4.4.0`), as `ci.yml` does for the actions. `pre-commit autoupdate --freeze` writes
   this form, but it also moves the hook to its newest tag. Check the commit against the tag on GitHub; it needs
   the network.
2. **`just`.** Either keep `rust-just` and give it a hash, which needs the hash of every wheel for Windows,
   macOS and Linux and `--require-hashes` for the whole of `requirements-dev.txt`
   ([task 048](048-builds-install-the-newest-dependencies.md) weighs the same choice for the builds), or use the
   official binary: download the release of `casey/just` for each OS in the Validate job and in a setup step for
   developers, check it with `sha256sum -c` against a hash written in the repo, and remove `rust-just` from
   `requirements-dev.txt`. The second changes [building.md](../../building.md#run-the-checks) and ADR-0012.

None of this sends a Twitch request.

## History

- 2026-10-21: Opened. Found while the dependency versions were listed and the source of `rust-just` was read
  from its metadata.
