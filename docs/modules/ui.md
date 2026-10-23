# `ui/`

**Purpose.** The parts of the tkinter window that `gui.py` builds. `gui.py` stays a file, because
`python gui.py` opens the preview, and its classes move here
([ADR-0020](../adr/ADR-0020-module-splits.md)). The window as a whole, `GUIManager` and the classes that are
still in `gui.py` are in [gui.md](gui.md). Every file here needs a display, so the package is outside the
coverage floor, as `gui.py` is.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | Imports the names listed in `__all__`. `gui.py` imports from `ui`, never from a file of it |
| `placeholder.py` | `PlaceholderEntry` and `PlaceholderCombobox` |
| `widgets.py` | `PaddedListbox`, `MouseOverLabel`, `LinkLabel`, `SelectCombobox` and `Notebook` |

## The generic widgets

Only the GUI uses them: `gui.py` and the files of this package.

- `PlaceholderEntry` is a `ttk.Entry` that shows `placeholder` in `placeholdercolor` (`grey60`) while it is
  empty. `get()` then returns an empty string. On focus it removes the placeholder and inserts `prefill`.
  `PlaceholderCombobox` is the same for a `ttk.Combobox`. The proxy field of the Settings tab is a
  `PlaceholderEntry`, and the game name fields of the Priority and Exclude lists are `PlaceholderCombobox`.
- `PaddedListbox` is a `tk.Listbox` inside a `tk.Frame`, so that it can have padding. `grid` and the other grid
  methods act on the frame. The four lists of the Settings tab are one each, and `configure_theme` sets their
  colors ([gui.md](gui.md#the-theme-and-dark-mode)).
- `MouseOverLabel` shows `alt_text` while the pointer is over it, or, with `reverse`, shows `alt_text` until
  the pointer is over it. On the Inventory tab it shows a campaign's end time and, on hover, its start time. An
  upcoming campaign shows its start time first.
- `LinkLabel` has the style `Link.TLabel` and opens `link` in the browser with `webopen` when it is clicked
  ([utils.md](utils.md#other-helpers)). With `style` set to an empty string it is a plain label that opens
  nothing, as the "Linked" status of a campaign on the Inventory tab is.
- `SelectCombobox` is a read-only `ttk.Combobox` as wide as its longest value, which calls `command` when a value
  is selected. The four drop-down lists of the Settings tab are one each.
- `Notebook` holds the `ttk.Notebook` of the four tabs. `GUIManager` keeps it as `tabs`.

**Dependencies.** Repo modules: `utils` (`webopen`); `gui` for type checking only. Third-party: none.
