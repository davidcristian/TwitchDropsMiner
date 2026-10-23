# Runbook: bringing in a fix from upstream

This project started as a fork of DevilXD/TwitchDropsMiner and is developed on its own
([ADR-0001](../adr/ADR-0001-independent-project.md)). Upstream still fixes problems this project has, most often
a GQL hash or a user agent that Twitch stopped accepting ([gql-operations.md](gql-operations.md)). This runbook
takes one upstream commit into `master` through a pull request of its own, because AGENTS.md asks for one
logical concern per pull request.

The rules, from [AGENTS.md](../../AGENTS.md#branches-pull-requests-and-remotes):

- The `upstream` remote is read only. Fetch from it, but never open an issue or a pull request there.
- A fix comes in by cherry-pick or by merge, never by rebasing `master` onto `upstream/master`. A rebase writes
  new commits for everything already on `master`, and publishing them needs a force-push, which AGENTS.md
  forbids for `master`.
- Upstream code is under the MIT License ([LICENSE.MIT](../../LICENSE.MIT)), which allows this AGPL project to
  include it. Keep the upstream author on the commit.

## Find the fix

1. Check the remotes. `upstream` must be `https://github.com/DevilXD/TwitchDropsMiner.git`:

   ```bash
   git remote -v
   ```

   If it is missing, add it with `git remote add upstream https://github.com/DevilXD/TwitchDropsMiner.git`.
2. Fetch upstream and list its commits that are not in `master` yet:

   ```bash
   git fetch upstream
   git cherry -v master upstream/master
   ```

   A line that starts with `+` is a commit that `master` lacks. A line that starts with `-` is a commit whose
   change `master` already has, from an earlier cherry-pick. `git log --oneline master..upstream/master` is not
   enough: a cherry-pick creates a new commit with another hash, so that command keeps listing picked commits.
   `git cherry` compares the patches, so a commit picked with a conflict resolution, or near lines that
   `master` changed, keeps its `+`.
3. Read the commit you want with `git show <commit>`.

## Pick it

1. Start from an up-to-date `master` and create a branch named for the fix:

   ```bash
   git switch master
   git pull --ff-only origin master
   git switch -c fix/<slug>
   ```

2. Pick the commit, without `-x`:

   ```bash
   git cherry-pick <commit>
   ```

   A plain cherry-pick keeps the upstream author and the upstream message unchanged, as AGENTS.md asks for
   commits taken from upstream. You become the committer. `-x` adds the line
   `(cherry picked from commit <hash>)` to the message, and AGENTS.md forbids commit hashes in commit messages.
3. If git stops with `The previous cherry-pick is now empty`, `master` already has the change. Run
   `git cherry-pick --skip` and stop here.
4. Run the checks in [AGENTS.md](../../AGENTS.md#what-every-change-must-pass). A change to `gui.py` needs the
   GUI check; without a display, follow [gui-preview-headless.md](gui-preview-headless.md).
5. Check the change against the hard rule in [AGENTS.md](../../AGENTS.md#the-one-hard-rule), which applies to
   picked code as well. If the pick sends more requests to Twitch, count them per cycle and write the count in
   the pull request description, because the picked message stays as upstream wrote it.
6. Push the branch and open the pull request on this repository:

   ```bash
   git push -u origin fix/<slug>
   gh pr create --repo davidcristian/TwitchDropsMiner --base master --title "<what changed>" --body "<why>"
   ```

   Without `--repo`, `gh` targets DevilXD/TwitchDropsMiner, because GitHub records this repository as its fork.

The pull request is merged with rebase merge. GitHub then writes new commits on `master`, so update your local
`master` with `git switch master` and `git pull --ff-only origin master` before the next branch.

## When the pick conflicts

This project changed `twitch.py` and `gui.py` after it split from upstream, for example to restart after a fatal
error, to detect installed games and to match list entries by pattern. A pick that touches these files can
conflict. Git then stops with:

```text
CONFLICT (content): Merge conflict in gui.py
error: could not apply <hash>... <subject>
```

1. List this project's own commits on the file, to see which of them the upstream commit conflicts with:

   ```bash
   git log --oneline upstream/master..master gui.py
   ```

2. Edit the file. Keep this project's behavior, and add the upstream commit's change to it. Where the two
   disagree, this project's code and AGENTS.md take precedence. Leave out a change to code this project
   removed, such as the password login `_AuthState._login`
   ([ADR-0010](../adr/ADR-0010-device-code-login.md)).
3. Mark the file as resolved and finish the pick. The commit keeps the upstream author and message:

   ```bash
   git add gui.py
   git cherry-pick --continue
   ```

4. If the upstream change does not fit this project's code, run `git cherry-pick --abort`. Then write the fix as
   this project's own commit, in the format in [AGENTS.md](../../AGENTS.md#commits). Name the upstream behavior
   in the message, not the upstream hash.

This project split `twitch.py` and other modules into packages of the same name
([ADR-0020](../adr/ADR-0020-module-splits.md)). A pick that touches such a module stops with:

```text
CONFLICT (modify/delete): twitch.py deleted in HEAD and modified in <hash> (<subject>).  Version <hash> (<subject>) of twitch.py left in tree.
```

Make the upstream change by hand in the file of the package that now holds the function. Then remove the
upstream copy of the module, mark the file as resolved and finish the pick, as in step 3:

```bash
git rm twitch.py
git add twitch/<file>.py
git cherry-pick --continue
```

After a resolved conflict in `gui.py`, run the GUI check again, because a wrong resolution in `gui.py` shows
only at runtime.

## Check the result

- `git cherry -v master upstream/master` marks the commit with `-` once the pull request is merged and your
  `master` is updated, unless its patch changed in the pick, as step 2 of [Find the fix](#find-the-fix) explains.
- The AGENTS.md checks pass on the branch, and the pull request description lists their commands and output.
- A fix that changes the requests the app sends to Twitch, such as a GQL hash, is confirmed only by a run with
  a login, as [gql-operations.md](gql-operations.md#check-the-result) describes.
