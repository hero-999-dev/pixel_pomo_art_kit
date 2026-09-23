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
# The edge of a message box that has something to warn about (#v2.8.0). The
# game has no red or yellow of its own; these are the same family's (the
# accent and BREAK are its green and sky), so they sit with the rest.
WARNING = "#f9e2af"
ERROR = "#f38ba8"

# One family, one size, for the whole kit. The family is NEVER swapped and a
# button's weight is NEVER dropped (#v2.8.0): switching language used to move
# chrome buttons to a lighter, smaller font, which read as the whole UI
# changing typeface. Only the point size may move now, and only inside a box
# that has been frozen first - see `Button.pin_box`.
FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "Helvetica"
FONT_SIZE = 9 if sys.platform.startswith("win") else 12
MIN_FONT_SIZE = 6

FONT = (FONT_FAMILY, FONT_SIZE)
FONT_BOLD = (FONT_FAMILY, FONT_SIZE, "bold")
FONT_SMALL = (FONT_FAMILY, max(7, FONT_SIZE - 1))
FONT_SMALL_BOLD = (FONT_FAMILY, max(7, FONT_SIZE - 1), "bold")
FONT_MONO = ("Consolas", 10) if sys.platform.startswith("win") else ("Menlo", 12)


def bold(size):
    """The kit's family, bold, at `size` - clamped so nothing goes invisible."""
    return (FONT_FAMILY, max(MIN_FONT_SIZE, int(size)), "bold")


def fit_bold(text, max_px, ceiling=None, master=None):
    """The largest BOLD font of the kit's one family whose `text` fits `max_px`.

    Family and weight are fixed inputs, never outputs: a translation that does
    not fit loses point size, not its typeface (#v2.8.0). If even
    `MIN_FONT_SIZE` overflows the text clips, because the box is the thing
    that must not move.

    `master` is the widget to measure through, and measuring goes straight to
    Tcl's `font measure` rather than through `tkinter.font.Font`. Two reasons:
    a `Font` object REGISTERS a named font with the interpreter, which is
    pointless churn for a throwaway measurement, and a bare `Font()` binds to
    `tkinter._default_root` — whichever root was created first, which in the
    test suite is very often one that has already been destroyed.

    With no `master` (or no interpreter at all) there is nothing to measure
    with, so the ceiling stands: a headless caller gets the full-size bold
    font rather than an exception."""
    ceiling = FONT_SIZE if ceiling is None else int(ceiling)
    if not text or max_px <= 0 or master is None:
        return bold(ceiling)
    for size in range(ceiling, MIN_FONT_SIZE - 1, -1):
        spec = bold(size)
        try:
            width = int(master.tk.call("font", "measure", spec, text))
        except (tk.TclError, RuntimeError, AttributeError, ValueError):
            return bold(ceiling)
        if width <= max_px:
            return spec
    return bold(MIN_FONT_SIZE)

IS_MAC = sys.platform == "darwin"


def setup(root):
    """Apply the theme to the root window: background, ttk scrollbar style,
    and the dark title bar on Windows.

    There is no menu styling here any more (#v2.8.0). It used to colour
    `tk.Menu` through the option database, which a Windows menu - a native
    control - only partly obeys; every menu and message box is the kit's own
    widget now (`dialogs.py`), in these tones by construction."""
    root.configure(bg=BG)
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


def icon(kind, size, colour, master=None):
    """A small glyph drawn smooth: "left", "right", "down" (solid triangles)
    or "close" (an X), `size` px square, in `colour` (#rrggbb), on a
    see-through ground - a PhotoImage, or None with no Pillow to draw it.

    Drawn at four times the size and scaled down, so its slanted edges are
    antialiased (#v2.8.0, ninth test pass: "pikselli duruyor"): a canvas
    polygon and a small x-glyph both come out stair-stepped on Windows, and a
    font's ▶ may be swapped for an emoji. The caller keeps the image alive."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    k = 4
    big = size * k
    rgb = tuple(int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    img = Image.new("RGBA", (big, big), rgb + (0,))
    pen = ImageDraw.Draw(img)
    m = big * 0.18                                  # margin
    if kind == "close":
        w = max(k, round(big * 0.13))
        pen.line((m, m, big - m, big - m), fill=rgb + (255,), width=w)
        pen.line((m, big - m, big - m, m), fill=rgb + (255,), width=w)
    else:
        lo, hi, mid = m, big - m, big / 2
        reach = (hi - lo) * 0.42                    # half the triangle's depth
        points = {"right": [(mid - reach, lo), (mid - reach, hi), (mid + reach, mid)],
                  "left": [(mid + reach, lo), (mid + reach, hi), (mid - reach, mid)],
                  "down": [(lo, mid - reach), (hi, mid - reach), (mid, mid + reach)]}[kind]
        pen.polygon(points, fill=rgb + (255,))
    # An average of each 4 x 4: the colour is the same everywhere (only the
    # alpha varies), so the edges soften and the colour stays exact.
    img = img.reduce(k)
    from art_kit import raster
    return raster.image_photo(img, master=master)


def unseen(window):
    """Map `window` see-through until `reveal`: built, measured, dark-titled
    and placed without being seen first where Windows puts a new window - the
    top-left corner - and then jumping to its place (#v2.8.0, eighth test
    pass: "sol üstten bir menü anlık gözüküp kayıyor"). `dark_title_bar`
    needs the window mapped, so withdrawing it instead would cost the dark
    title; where alpha is not supported it is withdrawn all the same."""
    try:
        window.attributes("-alpha", 0.0)
    except tk.TclError:
        window.withdraw()
        window._unseen_withdrawn = True


def reveal(window):
    """Show a window `unseen` made, where it now stands - undoing what
    `unseen` did and nothing more. A dialog is transient, and Tk keeps a
    transient withdrawn while its master is; deiconifying every withdrawn
    window here (v2.8.0's first cut) put a grabbed dialog on screen over a
    master that was not, which Tk 8.6 on macOS does not survive: closing it
    corrupted Tk's heap, and the next idle call crashed the process (v2.8.0's
    first Mac builds, whose tests keep the root withdrawn)."""
    try:
        window.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
    if getattr(window, "_unseen_withdrawn", False):
        window._unseen_withdrawn = False
        window.deiconify()


class held_paint:
    """`with theme.held_paint(root):` - nothing in the window repaints until
    the block ends, and then all of it repaints at once (#v2.8.0).

    For a change that moves many widgets together: the library folding away
    slides the whole canvas pane and everything in it 200 px sideways. Tk
    moves and repaints every child window one at a time, and on Windows the
    artist watches them go - buttons cut in half, then whole again. Held,
    the layout settles unseen and appears in one frame. WM_SETREDRAW is how
    Windows says "hold"; elsewhere this does nothing, and Aqua composites
    whole frames anyway."""

    def __init__(self, window):
        self._window = window
        self._hwnd = None

    def __enter__(self):
        if sys.platform.startswith("win"):
            try:
                import ctypes
                self._hwnd = ctypes.windll.user32.GetParent(self._window.winfo_id())
                ctypes.windll.user32.SendMessageW(self._hwnd, 0x000B, 0, 0)  # WM_SETREDRAW off
            except Exception:
                self._hwnd = None
        return self

    def __exit__(self, *_exc):
        if self._hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SendMessageW(self._hwnd, 0x000B, 1, 0)                # WM_SETREDRAW on
                # RDW_FRAME | RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW - and
                # not RDW_ERASE, which would blank every widget for the moment
                # before Tk repaints it: the very flash this is here to avoid.
                user32.RedrawWindow(self._hwnd, None, None, 0x0400 | 0x0001 | 0x0080 | 0x0100)
            except Exception:
                pass
        return False


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
        self._pin = None      # (width, height) in pixels once pin_box() ran
        self._pin_img = None  # the 1x1 image that makes width/height mean pixels
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

    def set_hover(self, on):
        """Wear (or drop) the hover colours with no pointer involved - the
        row the arrow keys have reached in a `dialogs.PopupMenu`."""
        if on:
            self._enter()
        else:
            self._leave()

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
        if self._pin is not None and "font" in kw and "text" not in kw:
            kw.pop("font")  # a pinned box picks its own size; see _refit
        result = tk.Label.configure(self, **kw)
        if self._hover and ("activebackground" in kw or "activeforeground" in kw):
            self._enter()  # a pressed tool under the pointer shows its new state at once
        if self._pin is not None and ("text" in kw or "font" in kw):
            self._refit()
        return result

    config = configure

    # --- a box that a translation cannot move (#v2.8.0) --------------------

    def _inset(self):
        """Padding + border + focus ring: the pixels around the display area."""
        def n(option):
            try:
                return int(str(self.cget(option)))
            except (tk.TclError, ValueError):
                return 0
        return (n("padx") + n("bd") + n("highlightthickness"),
                n("pady") + n("bd") + n("highlightthickness"))

    def pin_box(self, width=None, height=None):
        """Freeze this button's pixel box for good.

        Tk sizes a text Label in CHARACTERS, so a shorter word or a smaller
        font shrinks the widget - which is exactly what made the chrome jump
        on every language switch. A Label carrying an image takes `-width`
        and `-height` in PIXELS instead, so a 1x1 transparent image plus
        `compound="center"` turns this into a fixed box with text drawn in
        the middle of it. From here on the text changes and the point size
        follows (`_refit`); the box never does.

        Measured from the CURRENT layout, so a button stretched by
        `pack(fill="x")` keeps the width its parent gave it. `winfo_width` is
        1 on a window that was never mapped (the headless tests), so the
        requested size stands in there."""
        self.update_idletasks()
        ix, iy = self._inset()
        w = width if width is not None else self.winfo_width()
        h = height if height is not None else self.winfo_height()
        if w <= 1:
            w = self.winfo_reqwidth()
        if h <= 1:
            h = self.winfo_reqheight()
        w, h = max(1, w - 2 * ix), max(1, h - 2 * iy)
        self._pin = (w, h)
        if self._pin_img is None:
            # Held on the instance: a PhotoImage with no Python reference is
            # garbage-collected and the button goes blank.
            self._pin_img = tk.PhotoImage(master=self, width=1, height=1)
        tk.Label.configure(self, image=self._pin_img, compound="center",
                           width=w, height=h)
        self._refit()
        return self

    @property
    def pinned(self):
        return self._pin

    def _refit(self):
        if self._pin is None:
            return
        tk.Label.configure(self, font=fit_bold(self.cget("text"), self._pin[0], master=self))

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
