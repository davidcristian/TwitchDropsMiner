# Runbook: running the GUI preview without a display

`python gui.py` opens the window with mock data and no login
([building.md](../building.md#preview-the-gui)). Check 3 in
[AGENTS.md](../../AGENTS.md#what-every-change-must-pass) runs it for every GUI change. On Linux without a
display, such as an agent's shell or WSL without its GUI support (WSLg), the preview fails at startup. This
runbook runs it on Xvfb, an X server that draws into memory instead of onto a screen, and saves screenshots of
the window. Run every command from the repository folder, with the `env/` virtual environment from
[building.md](../building.md#set-up-the-environment).

## What the failure looks like

The first error comes from pystray, the tray icon library that `gui.py` imports:

```text
Xlib.error.DisplayNameError: Bad display name ""
```

On Linux `gui.py` tries pystray's AppIndicator, GTK and X11 backends in turn
([traybackend.md](../modules/traybackend.md)). Without the Gtk 3 introspection data, the first two print a
warning with `ValueError: Namespace Gtk not available`, and the X11 backend fails because no X display is set.
Without a DBus session bus, one warning names the bus instead, and only the X11 backend is tried.
With `PYSTRAY_BACKEND=dummy` set, tkinter fails next for the same reason:

```text
_tkinter.TclError: no display name and no $DISPLAY environment variable
```

## Run the preview

1. Check that tkinter and `xvfb-run` are installed:

   ```bash
   env/bin/python -c 'import tkinter; print(tkinter.TkVersion)'
   command -v xvfb-run
   ```

   The first prints the Tk version, such as `8.6`, and the second prints a path. The virtual environment uses
   the system's tkinter. On Debian and Ubuntu, install whatever is missing with
   `sudo apt install python3-tk xvfb`.
2. Run the preview for 30 seconds:

   ```bash
   PYSTRAY_BACKEND=dummy xvfb-run -a -s "-screen 0 1600x1000x24" timeout 30 env/bin/python gui.py; echo "exit=$?"
   ```

   - `PYSTRAY_BACKEND=dummy` selects pystray's dummy backend, which imports without errors and shows no tray
     icon.
   - `xvfb-run -a` starts Xvfb on a free display number and sets `DISPLAY` for the command.
   - `-s "-screen 0 1600x1000x24"` sets the screen size. In a test run the preview window was 1539 by 704
     pixels.
   - `timeout 30` ends the run, because the preview runs until its window is closed.

`exit=124` is the result to expect: `timeout` ended a preview that ran for 30 seconds without an error. An error
prints a traceback and gives `exit=1`. For example, a setting missing from the mock in `ui/preview.py` (see
the recipe in [AGENTS.md](../../AGENTS.md#recipes)) fails with:

```text
AttributeError: 'types.SimpleNamespace' object has no attribute 'restart_delay'
```

## Take a screenshot of the Main tab

A second process inside the same `xvfb-run` saves the whole virtual screen with Pillow, which `requirements.txt`
installs. Set `OUT` to a folder outside the repository. The 10 second wait gives the preview time to show its
mock data.

```bash
export OUT=/tmp/gui-shots
mkdir -p "$OUT"
PYSTRAY_BACKEND=dummy xvfb-run -a -s "-screen 0 1600x1000x24" sh -c '
  timeout 30 env/bin/python gui.py &
  sleep 10
  env/bin/python -c "import os, sys; from PIL import ImageGrab; ImageGrab.grab(xdisplay=os.environ[\"DISPLAY\"]).save(sys.argv[1])" "$OUT/main.png"
  wait'
```

## Take a screenshot of every tab

Switching tabs needs code, so this snippet runs `gui.py` with `ttk.Notebook.__init__` replaced. Ten seconds
after the window's only notebook is created, it selects each tab in turn and saves the window as `tab0.png` to
`tab3.png` in `$OUT`. Python reads the snippet from standard input, so no file is written into the repository.

```bash
PYSTRAY_BACKEND=dummy xvfb-run -a -s "-screen 0 1600x1000x24" timeout 30 env/bin/python - "$OUT" <<'EOF'
import os, sys, runpy
from tkinter import ttk
from PIL import ImageGrab

out = sys.argv[1]
notebook_init = ttk.Notebook.__init__

def show(nb, i):
    nb.select(i)
    nb.after(1500, grab, nb, i)

def grab(nb, i):
    top = nb.winfo_toplevel()
    x, y = top.winfo_rootx(), top.winfo_rooty()
    box = (x, y, x + top.winfo_width(), y + top.winfo_height())
    ImageGrab.grab(bbox=box, xdisplay=os.environ["DISPLAY"]).save(f"{out}/tab{i}.png")
    print(f"saved {out}/tab{i}.png", flush=True)
    if i + 1 < len(nb.tabs()):
        show(nb, i + 1)

def patched_init(self, *args, **kwargs):
    notebook_init(self, *args, **kwargs)
    self.after(10000, show, self, 0)

ttk.Notebook.__init__ = patched_init
runpy.run_path("gui.py", run_name="__main__")
EOF
```

It prints one `saved` line per tab: 0 is Main, 1 is Inventory, 2 is Settings and 3 is Help. Then `timeout` ends
the run with exit status 124. Open the PNG files in an image viewer, or with the file reading tool of an agent.

## Take the README pictures

The [Pictures](../../README.md#pictures) section of the README shows `main.png`, `inventory.png`, `settings.png`
and `help.png` from `docs/assets/`. They show the preview's mock data, in English and the light theme, in a
window of 1600 by 900 pixels, a common screen size. In the preview on Linux the Settings tab needs a window 1543
pixels wide to show every section without a scroll bar, and at 1280 pixels its Detected Games section is cut
off. This snippet works like the one above, but it waits 30 seconds, when the Main tab shows a drop one minute
from the end, and sets the window size first. It saves each picture with 256 colors into `docs/assets/`. That
makes each file 2 to 4 times smaller and changes only the edge pixels of text, by at most 30 of 255 levels in
a color channel:

```bash
PYSTRAY_BACKEND=dummy xvfb-run -a -s "-screen 0 1600x900x24" timeout 70 env/bin/python - docs/assets <<'EOF'
import os, sys, runpy
from tkinter import ttk
from PIL import Image, ImageGrab

out = sys.argv[1]
names = ["main", "inventory", "settings", "help"]
notebook_init = ttk.Notebook.__init__

def distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))

def save_small(image, path):
    # 256 colors: the 64 most frequent, then each far from the others, weighted by its count, so red text stays red
    counts = sorted(image.getcolors(1 << 24), reverse=True)
    weight = {color: count for count, color in counts}
    palette = [color for _, color in counts[:64]]
    nearest = {c: min(distance(c, p) for p in palette) for c in weight}
    while len(palette) < min(256, len(weight)):
        pick = max(weight, key=lambda c: nearest[c] * weight[c] ** 0.5)
        palette.append(pick)
        nearest = {c: min(d, distance(c, pick)) for c, d in nearest.items()}
    index = {c: min(range(len(palette)), key=lambda i: distance(c, palette[i])) for c in weight}
    small = Image.new("P", image.size)
    small.putpalette([channel for color in palette for channel in color])
    small.putdata([index[pixel] for pixel in image.get_flattened_data()])
    small.save(path, optimize=True)

def show(nb, i):
    nb.select(i)
    nb.after(2000, grab, nb, i)

def grab(nb, i):
    top = nb.winfo_toplevel()
    x, y = top.winfo_rootx(), top.winfo_rooty()
    box = (x, y, x + top.winfo_width(), y + top.winfo_height())
    save_small(ImageGrab.grab(bbox=box, xdisplay=os.environ["DISPLAY"]).convert("RGB"), f"{out}/{names[i]}.png")
    print(f"saved {out}/{names[i]}.png", flush=True)
    if i + 1 < len(names):
        show(nb, i + 1)

def start(nb):
    nb.winfo_toplevel().geometry("1600x900+0+0")
    nb.after(1500, show, nb, 0)

def patched_init(self, *args, **kwargs):
    notebook_init(self, *args, **kwargs)
    self.after(30000, start, self)

ttk.Notebook.__init__ = patched_init
runpy.run_path("gui.py", run_name="__main__")
EOF
```

Open each picture before you commit it, and check that it shows no real account, user ID or folder.

## Check the result

- The run of the preview prints `exit=124` and no traceback.
- The screenshots show the changed widget as intended.
- The report for check 3 lists the commands and their output. The runs change no file that git tracks, except
  the README pictures; they save the app icon, the only image of the mock, into the ignored `cache/` folder.
