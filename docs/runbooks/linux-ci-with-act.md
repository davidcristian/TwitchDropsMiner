# Runbook: running the Linux CI jobs with act

[act](https://github.com/nektos/act) runs the jobs of a GitHub Actions workflow in Docker containers on your own
machine. This runbook runs the two Ubuntu entries of the Validate job and the `linux-pyinstaller` job of
[`ci.yml`](../../.github/workflows/ci.yml) before a push, then starts each PyInstaller build. The Windows and
macOS jobs cannot run under act. The jobs download Python, packages and libXft and send no Twitch request, and
each build starts with no network. It was written on 2026-10-22 with act 0.2.89 and Docker Desktop on WSL 2,
where Docker runs arm64 images with QEMU.

Run every command from the repository folder. Set `ACT` to a folder outside the repository:

```bash
export ACT=/tmp/tdm-act
```

## Install act

```bash
mkdir -p "$ACT/bin"
(
  cd "$ACT/bin"
  release=https://github.com/nektos/act/releases/download/v0.2.89
  curl -fsSLO "$release/act_Linux_x86_64.tar.gz"
  curl -fsSLO "$release/checksums.txt"
  sha256sum -c --ignore-missing checksums.txt
  tar -xzf act_Linux_x86_64.tar.gz act
)
```

`sha256sum` prints `act_Linux_x86_64.tar.gz: OK`.

## Build the job images

act runs a job in an image of [catthehacker/docker_images](https://github.com/catthehacker/docker_images). These
images lack some packages and apt settings of GitHub's runner images that the jobs use, so build a derived image
for each runner label:

```bash
mkdir -p "$ACT/image"
cat > "$ACT/image/Dockerfile" <<'EOF'
ARG BASE
FROM ${BASE}
RUN echo 'APT::Get::Assume-Yes "true";' > /etc/apt/apt.conf.d/90assumeyes \
 && echo 'APT::Get::Always-Include-Phased-Updates "true";' > /etc/apt/apt.conf.d/99-phased-updates \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      xvfb xauth p7zip-full tk fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*
EOF
base=ghcr.io/catthehacker/ubuntu
docker build --platform linux/amd64 --build-arg BASE=$base:act-24.04 -t tdm-act:24.04 "$ACT/image"
docker build --platform linux/amd64 --build-arg BASE=$base:act-22.04 -t tdm-act:22.04 "$ACT/image"
docker build --platform linux/arm64 --build-arg BASE=$base:act-22.04 -t tdm-act:22.04-arm64 "$ACT/image"
```

| Addition | Why the jobs need it |
| --- | --- |
| `APT::Get::Assume-Yes` | `sudo apt install` in the build jobs has no `-y`. GitHub's images set this option in `configure-apt.sh` of actions/runner-images, and without it apt stops at its question. |
| `Always-Include-Phased-Updates` | GitHub's images set it too, so apt installs the same package versions. |
| `xvfb`, `xauth` | `xvfb-run`, which `just check` and the PyInstaller step call. |
| `p7zip-full` | `7z`, which creates the release zip file. |
| `tk` | The Tk library that the `tkinter` of `actions/setup-python`'s Python loads. |
| `fonts-noto-color-emoji` | The emoji font of GitHub's images, with which the window tests run. |

## Configure act

act reads its options from `actrc` in `$XDG_CONFIG_HOME/act`:

```bash
mkdir -p "$ACT/xdg/act"
cat > "$ACT/xdg/act/actrc" <<EOF
-P ubuntu-latest=tdm-act:24.04
-P ubuntu-22.04=tdm-act:22.04
-P ubuntu-22.04-arm=tdm-act:22.04-arm64
--pull=false
--action-cache-path=$ACT/actions
--cache-server-path=$ACT/cache
--artifact-server-path=$ACT/artifacts
--artifact-server-addr=127.0.0.1
EOF
```

- `-P` names the image of each `runs-on` label, and `--pull=false` uses the local images, which no registry has.
- The artifact server stores what `actions/upload-artifact` uploads. With Docker Desktop, a container reaches the
  host only at `host.docker.internal`, so the server listens on 127.0.0.1 and `run_act` below sets
  `ACTIONS_RUNTIME_URL` and `ACTIONS_RESULTS_URL`. act reads the two variables from its own environment and
  passes them to the jobs in place of the server's address.

## Copy the branch

```bash
rm -rf "$ACT/src"
git clone --quiet --branch "$(git branch --show-current)" --single-branch . "$ACT/src"
sed '/^    needs:$/{N;/\n      - validate$/d}' "$ACT/src/.github/workflows/ci.yml" > "$ACT/ci-alone.yml"
diff "$ACT/src/.github/workflows/ci.yml" "$ACT/ci-alone.yml"
```

- act copies its folder into each job container. A clone holds only committed files, and its `.git` folder lets
  the jobs run `git rev-parse`. A worktree does not work: its `.git` file names a folder outside the container.
- With `-j`, act also runs every job that the job names in `needs`. The copy of the workflow has no
  `needs: [validate]`, so a build job runs alone. `diff` prints the four removed pairs of lines.

## Run the jobs

```bash
run_act() {
  (cd "$ACT/src" && XDG_CONFIG_HOME="$ACT/xdg" \
    ACTIONS_RUNTIME_URL="http://host.docker.internal:$1/" ACTIONS_RESULTS_URL="http://host.docker.internal:$1/" \
    "$ACT/bin/act" workflow_dispatch --artifact-server-port "$1" "${@:2}")
}
docker volume rm -f act-toolcache
run_act 34567 -j validate --matrix os:ubuntu-latest --matrix python:PYTHON_VERSION
run_act 34567 -j validate --matrix os:ubuntu-latest --matrix python:BUILD_PYTHON_VERSION
docker volume rm -f act-toolcache
run_act 34568 -W "$ACT/ci-alone.yml" -j linux-pyinstaller --matrix arch:x86_64
run_act 34569 -W "$ACT/ci-alone.yml" -j linux-pyinstaller --matrix arch:aarch64 \
  --container-architecture linux/arm64
```

Each run ends with `Job succeeded`. On a machine with 24 threads, a Validate run took 40 seconds, the x86_64
build 85 seconds and the aarch64 build under QEMU 10 minutes. The two builds can run at the same time in two
shells, each with its own port.

- act keeps the Python of `actions/setup-python` in one Docker volume, `act-toolcache`, for every container.
  The Ubuntu 24.04 and 22.04 builds of a Python version share one folder there, so `docker volume rm -f` clears it
  between the Validate runs and the build runs. For the same reason, never run a Validate entry and the x86_64
  build at the same time. The x86_64 and aarch64 builds use the `x64` and `arm64` folders.
- After a failed run, act leaves its container. `docker ps -a` lists it with a name that starts with `act-`, and
  `docker rm -f` removes it.

These differences from GitHub's runners remain:

- act runs a job as root, and GitHub as the `runner` user. Eight tests that need file modes which root
  bypasses skip under act, so a Validate run shows 10 skipped tests where a run as another user shows 2.
- `actions/setup-python` downloads the newest patch release, and on GitHub it may use an older one from the
  image's tool cache.

## Start a build

The artifact zip file holds the release zip file, which holds the `Twitch Drops Miner` folder. This image is an
Ubuntu 22.04 with the libraries that PyInstaller leaves to the system's graphics stack
([task 061](../refinements/tasks/061-linux-build-needs-wayland-libraries.md)), fonts, an X server in memory and
Pillow for a screenshot:

```bash
mkdir -p "$ACT/run"
cat > "$ACT/run/Dockerfile" <<'EOF'
FROM ubuntu:22.04
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      xvfb xauth unzip python3-pil fontconfig-config fonts-dejavu-core fonts-noto-color-emoji \
      libxcb1 libwayland-client0 libwayland-cursor0 libwayland-egl1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 user
EOF
docker build --platform linux/amd64 -t tdm-run:amd64 "$ACT/run"
docker build --platform linux/arm64 -t tdm-run:arm64 "$ACT/run"
start_build() {
  name="Twitch.Drops.Miner.Linux.PyInstaller-$1"
  rm -rf "$ACT/start-$1" && mkdir -p "$ACT/start-$1"
  unzip -q -d "$ACT/start-$1" "$ACT/artifacts/1/$name/$name.zip"
  unzip -q -d "$ACT/start-$1" "$ACT/start-$1/$name.zip"
  docker run --rm --init --network none --platform "linux/$2" -u 1000:1000 -e HOME=/home/user \
    -v "$ACT/start-$1:/home/user" -w /home/user "tdm-run:$2" xvfb-run -a -s "-screen 0 1600x1000x24" sh -c '
      timeout 60 "./Twitch Drops Miner/Twitch Drops Miner" "$@" > app.log 2>&1 &
      sleep 20
      python3 -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=\"$DISPLAY\").save(\"shot.png\")"
      wait $!; echo "exit=$?"' sh "${@:3}"
}
start_build x86_64 amd64
start_build aarch64 arm64
```

Pass a flag after the platform to start the build with it, such as `start_build x86_64 amd64 --version`.
`--init` makes Docker's init process the first process of the container. Without it, `xvfb-run` is that
process and waits forever for the signal that Xvfb sends when it is ready.

## Check the result

- Each start prints `exit=124`: `timeout` ended an app that ran for a minute. `app.log` has no traceback.
- `shot.png` in `$ACT/start-<arch>` shows the window on the Main tab. With no network, the Output box lists
  `Cannot connect to Twitch, retrying in N seconds... (https://www.twitch.tv)`.
- With `--version`, the screenshot shows a dialog with the version and the short commit hash, such as
  `v16.dev.61d04a9`. The dialog has the error icon
  ([task 025](../refinements/tasks/025-version-and-help-shown-as-error.md)).

To clean up, remove the images, the volume and the folder:

```bash
docker image rm tdm-act:24.04 tdm-act:22.04 tdm-act:22.04-arm64 tdm-run:amd64 tdm-run:arm64
docker volume rm -f act-toolcache
rm -rf "$ACT"
```
