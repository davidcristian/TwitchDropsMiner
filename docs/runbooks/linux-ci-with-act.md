# Runbook: running the Linux CI jobs with act

[act](https://github.com/nektos/act) runs the jobs of a GitHub Actions workflow in Docker containers on your own
machine. This runbook runs the two Ubuntu entries of the Validate job and the `linux-pyinstaller` and
`linux-appimage` jobs of [`ci.yml`](../../.github/workflows/ci.yml) before a push, then starts each build. The
Windows and macOS jobs cannot run under act. The jobs download Python, packages, Ubuntu packages, libXft, the
AppImage runtime and AppRun, and send no Twitch request, and each build starts with no network. It was written
on 2026-10-22 with act 0.2.89 and Docker Desktop on WSL 2, where Docker runs arm64 images with QEMU.

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

act runs a job as the default user of its image, which is root in these images, and GitHub runs it as the user
`runner`. As root, the `linux-appimage` job fails: pip installs appimage-builder into Ubuntu's system folder, and
the check of the user's site folder prints `installcheck: no package found, so nothing was checked`. So that job
runs in an image with a user `runner`. act changes the owner of the copied repository to that user before the
first step:

```bash
mkdir -p "$ACT/user-image"
cat > "$ACT/user-image/Dockerfile" <<'EOF'
ARG BASE
FROM ${BASE}
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-dev fakeroot squashfs-tools \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1001 -s /bin/bash runner \
 && echo 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner \
 && chmod 0440 /etc/sudoers.d/runner
USER runner
ENV USER=runner RUNNER_USER=runner HOME=/home/runner PATH=/home/runner/.local/bin:${PATH}
EOF
docker build --platform linux/amd64 --build-arg BASE=tdm-act:22.04 -t tdm-act-user:22.04 "$ACT/user-image"
docker build --platform linux/arm64 --build-arg BASE=tdm-act:22.04-arm64 -t tdm-act-user:22.04-arm64 \
  "$ACT/user-image"
```

| Addition | Why the AppImage job needs it |
| --- | --- |
| `runner` with `sudo` and no password | The job's `sudo apt` lines, and a pip that installs into `~/.local`. |
| `~/.local/bin` first in `PATH` | pip puts the `appimage-builder` command there. GitHub's images add this folder to `PATH`. |
| `python3-dev` | The headers with which pip builds pycairo and PyGObject for Ubuntu's Python. Without them, pycairo stops with `ERROR: Python dependency not found`. GitHub's `install-python.sh` installs it. |
| `fakeroot` | appimage-builder stops with `Could not find 'fakeroot' on $PATH` before it unpacks the Ubuntu packages. GitHub's images list it. |
| `squashfs-tools` | `mksquashfs`, which appimage-builder runs to create the image. The job does not install it, so GitHub's images have it. |

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
- Under QEMU, `ldconfig` sometimes stops with `qemu: uncaught target signal 11 (Segmentation fault)`. In the
  aarch64 build, PyInstaller finds a library in `/usr/lib/aarch64-linux-gnu` only through `ldconfig -p`, so when
  that call stops, the build fails with `ValueError: Could not resolve any shared library of Gio 2.0`. The call
  stopped in 2 of 20 tries, and on 2026-10-22 the build failed this way in three runs in a row. Run it again.

The AppImage jobs run in the images with the user `runner`. A `-P` option on the command line replaces the one
for the same label in `actrc`:

```bash
run_act 34570 -W "$ACT/ci-alone.yml" -j linux-appimage --matrix arch:x86_64 \
  -P ubuntu-22.04=tdm-act-user:22.04 | tee "$ACT/appimage-x86_64.log"
run_act 34571 -W "$ACT/ci-alone.yml" -j linux-appimage --matrix arch:aarch64 \
  --container-architecture linux/arm64 -P ubuntu-22.04-arm=tdm-act-user:22.04-arm64 \
  | tee "$ACT/appimage-aarch64.log"
grep -hE ': OK$|Downloading:|Success - Main Check that the AppImage' "$ACT"/appimage-*.log
```

Each run ends with `Job succeeded`, after 80 seconds for `x86_64` and 6.5 minutes for `aarch64` under QEMU.
`grep` prints, for each architecture, an `OK` line for the runtime, AppRun, its hooks library and the libXft
archive, and the `Success` lines of the two steps that compare the AppImage with the checked files and with
`constraints.txt`. It prints no `Downloading:` line: appimage-builder downloads the runtime or AppRun only when
the recipe has not put a checked copy in its build folder ([building.md](../building.md#build-the-appimage)).

These differences from GitHub's runners remain:

- act runs the Validate and PyInstaller jobs as root, and GitHub as the `runner` user. Eight tests that need
  file modes which root bypasses skip under act, so a Validate run shows 10 skipped tests where a run as another
  user shows 2.
- The act images have Ubuntu's pipx package, and GitHub's images install pipx with pip. So in the AppImage job,
  pip prints a dependency conflict between pipx and argcomplete, which does not stop the job.
- `actions/setup-python` downloads the newest patch release, and on GitHub it may use an older one from the
  image's tool cache.

## Start a build

The artifact zip file holds the release zip file, which holds the `Twitch Drops Miner` folder. This image is an
Ubuntu 22.04 with the libraries that PyInstaller and appimage-builder leave to the system's graphics stack
([task 061](../refinements/tasks/061-linux-build-needs-wayland-libraries.md)), fonts, an X server in memory,
DBus for a session bus and Pillow for a screenshot:

```bash
mkdir -p "$ACT/run"
cat > "$ACT/run/Dockerfile" <<'EOF'
FROM ubuntu:22.04
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      xvfb xauth unzip python3-pil fontconfig-config fonts-dejavu-core fonts-noto-color-emoji \
      libxcb1 libxcb-render0 libwayland-client0 libwayland-cursor0 libwayland-egl1 dbus \
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
      export DBUS_SESSION_BUS_ADDRESS="$(dbus-daemon --session --fork --print-address)"
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
process and waits forever for the signal that Xvfb sends when it is ready. `dbus-daemon` starts the session bus
that a desktop has. Without it, the app uses pystray's X11 backend and prints a line that starts with
`Tray icon:` ([traybackend.md](../modules/traybackend.md)). With it, GTK prints a `dbind-WARNING` because the
container has no accessibility bus, which does not affect the app.

## Start an AppImage

```bash
start_appimage() {
  name="Twitch.Drops.Miner.Linux.AppImage-$1"
  dir="$ACT/start-appimage-$1"
  rm -rf "$dir" && mkdir -p "$dir"
  unzip -q -d "$dir" "$ACT/artifacts/1/$name/$name.zip"
  unzip -q -d "$dir" "$dir/$name.zip"
  if [ "$2" = arm64 ]; then
    printf '\0\0\0' | dd of="$dir/Twitch Drops Miner/Twitch.Drops.Miner-$1.AppImage" bs=1 seek=8 conv=notrunc
  fi
  docker run --rm --init --network none --platform "linux/$2" -u 1000:1000 -e HOME=/home/user \
    -e APPIMAGE_EXTRACT_AND_RUN=1 -v "$dir:/home/user" -w /home/user "tdm-run:$2" \
    xvfb-run -a -s "-screen 0 1600x1000x24" sh -c '
      export DBUS_SESSION_BUS_ADDRESS="$(dbus-daemon --session --fork --print-address)"
      timeout 60 "./Twitch Drops Miner/Twitch.Drops.Miner-$0.AppImage" "$@" > app.log 2>&1 &
      sleep 20
      python3 -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=\"$DISPLAY\").save(\"shot.png\")"
      wait $!; echo "exit=$?"
      while pgrep -x python3 > /dev/null; do sleep 1; done' "$1" "${@:3}"
}
start_appimage x86_64 amd64
start_appimage aarch64 arm64
```

- The container has no FUSE device, so `APPIMAGE_EXTRACT_AND_RUN=1` makes the AppImage extract its files into
  `/tmp` and start from there. A flag after the platform goes to the app, as for `start_build`.
- In this mode, the app runs as a child of the AppImage runtime. `timeout` sends SIGTERM to both, because they
  are in its process group, and the `pgrep` loop waits until the app has saved its files and ended. A SIGTERM
  to the runtime alone reaches the app too, except under QEMU ([parentexit.md](../modules/parentexit.md)).
- Docker's QEMU entry for arm64 runs only an ELF file with zeros in bytes 8 to 15 of its header. An AppImage
  has its magic bytes `AI` and 2 at bytes 8 to 10, so `dd` sets them to zero in the copy. Without that, `sh`
  reads the file as a script and prints `Syntax error: "(" unexpected`. The `x86_64` AppImage starts unchanged.

## Check the result

- Each start prints `exit=124`: `timeout` ended an app that ran for a minute. `app.log` has no traceback and
  no line that starts with `Tray icon:`, so pystray's AppIndicator backend loaded
  ([traybackend.md](../modules/traybackend.md)).
- `shot.png` in `$ACT/start-<arch>` and `$ACT/start-appimage-<arch>` shows the window on the Main tab. With no
  network, the Output box lists `Cannot connect to Twitch, retrying in N seconds... (https://www.twitch.tv)`.
- With `--version`, the screenshot shows a dialog with the version and the short commit hash, such as
  `v16.dev.61d04a9`. The dialog has the error icon
  ([task 025](../refinements/tasks/025-version-and-help-shown-as-error.md)).
- After a start without a flag, each build has written `cookies.jar`, `settings.json`, `lock.file` and `cache/`
  next to its executable or `.AppImage` file.

To clean up, remove the images, the volume and the folder:

```bash
docker image rm tdm-act:24.04 tdm-act:22.04 tdm-act:22.04-arm64 tdm-act-user:22.04 tdm-act-user:22.04-arm64 \
  tdm-run:amd64 tdm-run:arm64
docker volume rm -f act-toolcache
rm -rf "$ACT"
```
