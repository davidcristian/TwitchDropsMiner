# `parentexit.py`

**Purpose.** Without FUSE, an AppImage started with `--appimage-extract-and-run` or `APPIMAGE_EXTRACT_AND_RUN=1`
extracts its files into a temporary folder and starts the app as a child process. The AppImage runtime, the
program at the start of the `.AppImage` file, then waits for the app and passes no signal on to it. So a
SIGTERM from `kill` or `pkill` to the started process ends only the runtime, and the app keeps running without
saving `settings.json` and `cookies.jar`. `end_with_runtime` asks the kernel to send the
app SIGTERM when its parent ends (`PR_SET_PDEATHSIG` of `prctl`), so the SIGTERM handler of `main.py` closes the
app. No release of the runtime passes a signal on in this mode
([building.md](../building.md#build-the-appimage)). Through FUSE, the runtime runs the app in its own process,
and a SIGTERM reaches the app directly.

## Public contract

- `end_with_runtime(platform, environ, calls)` returns whether the app's parent is the AppImage runtime.
  `main.py` calls it with `sys.platform`, `os.environ` and `LinuxProcess()`, before it imports `truststore` and
  the app's modules ([main.md](main.md#startup-order)).
  - It returns False and calls nothing when `platform` is not `linux` or `environ` has no `APPIMAGE`.
  - It returns False and requests nothing when the parent runs another file than `APPIMAGE`, as through FUSE,
    where the parent is the program that started the AppImage, or when reading the parent's file or the
    request raises `OSError`.
  - Otherwise it requests SIGTERM at the parent's end and returns True. When the parent ID has changed after the
    request, the runtime ended before it, and it sends SIGTERM to the app at once.
- `ProcessCalls` is the `Protocol` of the calls it makes: `parent_id()`, `executable(pid)`,
  `signal_on_parent_exit(signum)` and `signal_self(signum)`. Tests pass a fake one.
- `LinuxProcess` makes them with `os.getppid`, `os.readlink` of `/proc/<pid>/exe`, `prctl` from the C library
  through `ctypes`, and `os.kill`.

## Invariants

- The runtime sets `APPIMAGE` to what it reads from its own `/proc/self/exe`, so `/proc/<pid>/exe` of the
  parent equals `APPIMAGE` only when the parent is the runtime.
- The kernel keeps the request across `execve` and clears it in a child process, so the folder dialog's child
  ([folderpicker.md](folderpicker.md)) does not inherit it.
- A SIGTERM that `timeout` sends to its process group, or systemd to every process of a service, reaches the
  app directly and again from the kernel when the runtime ends. `main.py` keeps its SIGTERM handler until the files
  are saved, so the second one does not end the app during its shutdown ([main.md](main.md#the-run-and-the-exit)).
- A SIGTERM before `main()` sets its handler ends the app with the default action, as a SIGTERM through FUSE does
  at that time. The window handles no input before then, so no setting has changed.
- When the runtime ends during the first imports of `main.py`, before the request, the parent is no longer the
  runtime, and the app keeps running until it is closed in another way.
- Under QEMU user emulation, such as Docker's arm64 containers on an x86_64 host, `/proc/<pid>/exe` of every
  emulated process names `qemu-aarch64`, so `end_with_runtime` requests nothing there.
- A runtime ended by a signal does not remove its temporary folder, `appimage_extracted_<md5>` in `$TMPDIR` or
  `/tmp`. The next start of the same file uses it again.

`tests/test_parentexit.py` checks each case with a fake, and on Linux kills a stand in for the runtime and checks
that its child receives SIGTERM.

**Dependencies.** None: the standard library only.
