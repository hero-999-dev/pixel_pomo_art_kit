"""Pixel Pomo's MATCHA theme, for the kit's own widgets (#v2.4.0).

The tones are the game's (`PixelTheme.matcha` in logic.dart), copied rather
than approximated, so the kit and the app the art ships into look like one
product. Everything visual in app.py goes through here: a colour is named
once, and a widget is styled by one helper rather than by seven keyword
arguments repeated at every call site.

Plain `tk` widgets are used for almost everything because they take `bg`/`fg`
on every platform. The two exceptions are documented where they live:

* **Scrollbars** are `ttk` on the `clam` theme. A classic `tk.Scrollbar` is a
  native control on Windows and macOS and ignores every colour option, which
  is exactly the grey bar the artist complained about.
* **Swatches** are `tk.Label`s, never `tk.Button`s. On macOS the Aqua button is
  a native control and ignores `bg`, so every ready colour rendered as a white
  pill (#v2.4.0 "ready colours gözükmüyor hepsi beyaz").
"""
import sys
import tkinter as tk
from tkinter import ttk

# --- the palette -----------------------------------------------------------
BG = "#1a2420"            # window background
PANEL = "#2a3a30"         # raised panels, buttons at rest
PANEL_HI = "#35483c"      # hover / pressed
ACCENT = "#a6e3a1"        # the selected tool, active things
WORK = "#94d977"          # the "work" green - secondary accent
BREAK = "#89dceb"         # the "break" blue - informational
ON_SURFACE = "#cad9c4"    # body text
ON_DIM = "#9db09a"        # captions, hints
ON_ACCENT = "#1a2420"     # text on top of ACCENT
SHADOW = "#0f1611"        # borders, the darkest tone
CANVAS_BG = "#141c18"     # behind the checkerboard
CHECKER = ("#232f28", "#2a3a30")
SELECTED_ROW = "#3a5f3a"

FONT = ("Segoe UI", 9) if sys.platform.startswith("win") else ("Helvetica", 12)
FONT_BOLD = (FONT[0], FONT[1], "bold")
FONT_SMALL = (FONT[0], max(7, FONT[1] - 1))
FONT_MONO = ("Consolas", 10) if sys.platform.startswith("win") else ("Menlo", 12)

IS_MAC = sys.platform == "darwin"


def setup(root):
    """Apply the theme to the root window: background, option database (so
    menus and dialogs pick the tones up too), ttk scrollbar style, and the
    dark title bar on Windows."""
    root.configure(bg=BG)
    # Menus are created by Tk with its own defaults; the option database is
    # the only way to colour every one of them (including the ⋮ menus) once.
    for pattern, value in (
            ("*Menu.background", PANEL), ("*Menu.foreground", ON_SURFACE),
            ("*Menu.activeBackground", ACCENT), ("*Menu.activeForeground", ON_ACCENT),
            ("*Menu.borderWidth", 0), ("*Menu.relief", "flat"),
            ("*Menu.activeBorderWidth", 0),
            ("*Menu.selectColor", ACCENT)):
        root.option_add(pattern, value)
    _style_scrollbars(root)
    dark_title_bar(root)


def _style_scrollbars(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # the one built-in theme that honours colours
    except tk.TclError:
        pass
    common = dict(background=PANEL_HI, troughcolor=BG, bordercolor=BG,
                  lightcolor=PANEL_HI, darkcolor=PANEL_HI, arrowcolor=ON_DIM,
                  relief="flat", gripcount=0)
    style.configure("Matcha.Vertical.TScrollbar", **common)
    style.configure("Matcha.Horizontal.TScrollbar", **common)
    for name in ("Matcha.Vertical.TScrollbar", "Matcha.Horizontal.TScrollbar"):
        style.map(name,
                  background=[("active", ACCENT), ("pressed", ACCENT)],
                  arrowcolor=[("active", ON_ACCENT)])


def dark_title_bar(window):
    """Windows 10/11 paint the title bar white (or the user's accent colour)
    unless told otherwise. Tk has no option for it; DwmSetWindowAttribute
    does. Works for the root and for any Toplevel (the dialogs). Best effort
    — a failure here is cosmetic, so it is swallowed."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
        # Windows 11 also lets the caption colour be set outright.
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36
        def _colorref(hexcol):
            r, g, b = int(hexcol[1:3], 16), int(hexcol[3:5], 16), int(hexcol[5:7], 16)
            return ctypes.c_int(r | (g << 8) | (b << 16))
        cap = _colorref(BG)
        txt = _colorref(ON_SURFACE)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(cap), ctypes.sizeof(cap))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_TEXT_COLOR, ctypes.byref(txt), ctypes.sizeof(txt))
    except Exception:
        pass


# --- widget helpers ----------------------------------------------------------

def frame(parent, **kw):
    kw.setdefault("bg", BG)
    return tk.Frame(parent, **kw)


def label(parent, text="", dim=False, **kw):
    kw.setdefault("bg", BG)
    kw.setdefault("fg", ON_DIM if dim else ON_SURFACE)
    kw.setdefault("font", FONT_SMALL if dim else FONT)
    return tk.Label(parent, text=text, **kw)


class Button(tk.Label):
    """A flat matcha button, built on a Label.

    Not a `tk.Button`: on macOS that is a native Aqua control which ignores
    `bg`, `fg` and `relief`, so every button would come out as a white pill
    and the selected tool would look like every other tool. A Label honours
    its colours on every platform. It keeps the `command` option and
    `invoke()` so callers can treat it like a Button."""

    def __init__(self, parent, text="", command=None, **kw):
        self._command = command
        kw.setdefault("bg", PANEL)
        kw.setdefault("fg", ON_SURFACE)
        kw.setdefault("activebackground", PANEL_HI)
        kw.setdefault("activeforeground", kw["fg"])
        kw.setdefault("highlightbackground", kw["bg"])
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("relief", "flat")
        kw.setdefault("bd", 0)
        kw.setdefault("font", FONT_BOLD)
        kw.setdefault("padx", 6)
        kw.setdefault("pady", 4)
        kw.setdefault("cursor", "hand2")
        kw.setdefault("anchor", "center")
        super().__init__(parent, text=text, **kw)
        self._rest = {"bg": kw["bg"], "fg": kw["fg"]}  # colours when not hovered
        self._hover = False
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", lambda e: self.invoke())

    def _enter(self, _e=None):
        self._hover = True
        tk.Label.configure(self, bg=self.cget("activebackground"),
                           fg=self.cget("activeforeground"))

    def _leave(self, _e=None):
        self._hover = False
        tk.Label.configure(self, **self._rest)

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if "command" in kw:
            self._command = kw.pop("command")
        for alias, key in (("background", "bg"), ("foreground", "fg")):
            if alias in kw:
                kw[key] = kw.pop(alias)
        for key in ("bg", "fg"):
            if key in kw:
                self._rest[key] = kw[key]
                if self._hover:
                    kw.pop(key)  # keep the hover colours until the pointer leaves
        if not kw:
            return tk.Label.configure(self)
        result = tk.Label.configure(self, **kw)
        if self._hover and ("activebackground" in kw or "activeforeground" in kw):
            self._enter()  # a pressed tool under the pointer shows its new state at once
        return result

    config = configure

    def invoke(self):
        if self._command is not None and str(self.cget("state")) != "disabled":
            return self._command()


def button(parent, text, command, **kw):
    btn = Button(parent, text, command, **kw)
    return btn


def set_pressed(btn, pressed):
    """The selected-tool look: accent face, dark text. Not `relief=sunken` -
    Aqua ignores relief, and a one-pixel bevel is not a state anyone can
    read at a glance anyway (#v2.4.0, item 12)."""
    if pressed:
        btn.configure(bg=ACCENT, fg=ON_ACCENT, activebackground=ACCENT,
                      activeforeground=ON_ACCENT, highlightbackground=ACCENT)
    else:
        btn.configure(bg=PANEL, fg=ON_SURFACE, activebackground=PANEL_HI,
                      activeforeground=ON_SURFACE, highlightbackground=PANEL)


def swatch(parent, hexcol, command, size=1, **kw):
    """A clickable colour square. A `tk.Label` with a coloured background,
    because that is honoured on macOS where a `tk.Button`'s is not."""
    hexcol = hexcol if hexcol.startswith("#") else f"#{hexcol}"
    w = tk.Label(parent, bg=hexcol.lower(), width=2 * size, height=size,
                 relief="flat", bd=0, highlightthickness=1,
                 highlightbackground=SHADOW, cursor="hand2", **kw)
    w.bind("<Button-1>", lambda e: command())
    return w


def scrollbar(parent, orient):
    style = "Matcha.Vertical.TScrollbar" if orient == "vertical" else "Matcha.Horizontal.TScrollbar"
    return ttk.Scrollbar(parent, orient=orient, style=style)


def entry(parent, **kw):
    kw.setdefault("bg", PANEL)
    kw.setdefault("fg", ON_SURFACE)
    kw.setdefault("insertbackground", ON_SURFACE)
    kw.setdefault("selectbackground", ACCENT)
    kw.setdefault("selectforeground", ON_ACCENT)
    kw.setdefault("relief", "flat")
    kw.setdefault("bd", 0)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("highlightbackground", SHADOW)
    kw.setdefault("highlightcolor", ACCENT)
    kw.setdefault("font", FONT_MONO)
    return tk.Entry(parent, **kw)


def separator(parent, orient="vertical"):
    """A one-pixel accent-dim line. The tools pane hangs one down its left
    edge, from the very top to the very bottom (#v2.4.0, item 3)."""
    if orient == "vertical":
        return tk.Frame(parent, bg=PANEL_HI, width=1)
    return tk.Frame(parent, bg=PANEL_HI, height=1)


def readable_on(hexcol):
    """Black or white, whichever reads on `hexcol`."""
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#000000" if (r * 299 + g * 587 + b * 114) > 128000 else "#ffffff"


def right_click_events():
    """The secondary-button events for this platform. macOS Tk reports a
    right click (or two-finger tap) as Button-2, not Button-3; Control-click
    is the one-button-mouse convention there. Binding all of them costs
    nothing and means the eyedropper works on every machine."""
    if IS_MAC:
        return ("<Button-2>", "<Button-3>", "<Control-Button-1>")
    return ("<Button-3>",)


def modifier():
    """'Command' on macOS, 'Control' elsewhere — for the Ctrl/Cmd shortcuts."""
    return "Command" if IS_MAC else "Control"


def modifier_label():
    return "Cmd" if IS_MAC else "Ctrl"
