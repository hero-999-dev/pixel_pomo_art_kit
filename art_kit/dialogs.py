"""The kit's own popup menus and message boxes (#v2.8.0).

`tk.Menu`, `messagebox`, `simpledialog` and `colorchooser` are native
controls on Windows: whatever the option database says, they come up in the
system's grey-and-highlight look, in the system font, and read as a
different program opening over the kit ("çıkan menü gri kırmızı klasik
menü"). Everything here is drawn with the MATCHA widgets from `theme`
instead, and keeps the call shapes of the modules it replaces, so a call
site changes its module name and nothing else.

The dialogs are modal and synchronous (`wait_window`), exactly like the
native ones, so `if askyesno(...)` still reads top to bottom.

The one popup still native is the file picker behind IMPORT PNG and the
exports. That is Explorer's own window - Quick Access, search, OneDrive, the
artist's pinned folders - and a Tk-drawn copy would be a worse tool in a
nicer colour.
"""
import sys
import tkinter as tk

from art_kit import theme
from art_kit.i18n import t

TITLE = "Pixel Pomo Art Kit"
MENU_MIN_W = 160    # px: about what a native menu of these labels measures
# A tick row's box, ticked or not. The two glyphs come from one font and are
# the same width, so the labels after them line up either way.
TICKED, UNTICKED = "☑", "☐"
DIALOG_MIN_W = 300  # px: so a one-line message is not a sliver under its title

# The strip down a message's left edge: the icon a native box has, in the
# kit's own tones.
KIND_COLOURS = {"info": theme.ACCENT, "warning": theme.WARNING, "error": theme.ERROR}


def _root(parent):
    return parent if parent is not None else tk._default_root


def _work_area(widget, x, y):
    """(left, top, right, bottom) of the screen the point (x, y) is on.

    Windows can say which monitor a point belongs to; Tk only knows the
    primary screen, and clamping a menu to that would throw one opened on a
    second monitor back onto the first. Everywhere else the primary screen
    is the answer Tk has."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

            # A private handle, so these signatures are not imposed on
            # anything else in the process that calls user32.
            user32 = ctypes.WinDLL("user32")
            user32.MonitorFromPoint.restype = wintypes.HANDLE
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
            nearest = 2  # MONITOR_DEFAULTTONEAREST
            monitor = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), nearest)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                work = info.rcWork
                return work.left, work.top, work.right, work.bottom
        except (OSError, AttributeError, ValueError):
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def place_menu(x, y, w, h, area, flip_y=None):
    """Where a `w` x `h` menu asked for at (x, y) actually goes, inside `area`.

    Below and to the right of the point, like a native menu. If it would run
    off the bottom it opens UPWARDS instead - ending at `flip_y`, the top of
    the button it hangs from, so it never covers that button; with no button,
    ending at the point itself."""
    left, top, right, bottom = area
    x, y = int(x), int(y)
    if y + h > bottom:
        y = (y if flip_y is None else int(flip_y)) - h
    return max(left, min(x, right - w)), max(top, min(y, bottom - h))


class PopupMenu:
    """A drop-down list in the kit's colours, with `tk.Menu`'s methods.

    Items are only recorded until `tk_popup`: the library builds one menu per
    row, and a Toplevel per row would be dozens of hidden windows.

    The row under the pointer - or the one the arrow keys moved to - wears
    the accent, the way the selected tool does. A click or Enter runs it;
    Escape, a click anywhere else, or the kit losing focus closes the menu,
    the way a native one closes. A tick row (`add_checkbutton`) is the
    exception: it runs and the menu STAYS, with every tick re-read, because
    ticking several things is the point of a checklist.

    A label may be a callable, read each time the menu is posted - so a menu
    built once (one per library row) speaks the language chosen since.
    `on_close` is called whenever a posted menu goes away, however it went."""

    def __init__(self, parent, tearoff=False, on_close=None):
        self._parent = parent
        self._on_close = on_close
        # ("command", label, command) | ("check", label, command, checked, fg)
        # | ("caption", label) | ("separator",)
        self._items = []
        self._win = None
        self._rows = []    # the posted menu's rows as (row, command), top to bottom
        self._ticks = {}   # row index -> (label, checked) for the tick rows
        self._active = None

    def add_command(self, label, command=None):
        self._items.append(("command", label, command))

    def add_checkbutton(self, label, checked, command=None, fg=None):
        """A row with a box in front, ticked while `checked()` is true; `fg`
        colours its text - an artist's row in that artist's colour."""
        self._items.append(("check", label, command, checked, fg))

    def add_caption(self, label):
        """A dim heading over a group of rows. Not a row: nothing to click,
        and the arrow keys pass it by."""
        self._items.append(("caption", label))

    def add_separator(self):
        self._items.append(("separator",))

    def labels(self):
        """The labels of the rows one can choose, top to bottom."""
        return [self._text(item[1]) for item in self._items if item[0] in ("command", "check")]

    @staticmethod
    def _text(label):
        return label() if callable(label) else label

    @staticmethod
    def _tick_text(label, on):
        return f"{TICKED if on else UNTICKED}  {label}"

    def tk_popup(self, x, y, flip_y=None):
        """Show the menu with its top-left corner at screen point (x, y).
        `flip_y` is the top of the button it drops from; see `place_menu`."""
        self.unpost()
        win = tk.Toplevel(self._parent, bg=theme.SHADOW)
        # See-through until placed: no flash in the corner (#v2.8.0). Not
        # withdrawn - Tk will not show again an override-redirect window that
        # was measured while withdrawn.
        theme.unseen(win)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        self._win = win
        self._rows, self._ticks, self._active = [], {}, None
        body = tk.Frame(win, bg=theme.PANEL)
        body.pack(padx=1, pady=1)   # the one-pixel SHADOW edge
        tk.Frame(body, bg=theme.PANEL, width=MENU_MIN_W, height=0).pack()
        for item in self._items:
            if item[0] == "separator":
                tk.Frame(body, bg=theme.PANEL_HI, height=1).pack(fill="x", padx=6, pady=3)
                continue
            if item[0] == "caption":
                tk.Label(body, text=self._text(item[1]), bg=theme.PANEL, fg=theme.ON_DIM, anchor="w",
                         font=theme.FONT_SMALL_BOLD, padx=12, pady=1).pack(fill="x", pady=(3, 0))
                continue
            index = len(self._rows)
            label, command = self._text(item[1]), item[2]
            fg = theme.ON_SURFACE
            if item[0] == "check":
                self._ticks[index] = (label, item[3])
                text, click = self._tick_text(label, item[3]()), lambda i=index: self._toggle(i)
                fg = item[4] or fg
            else:
                text, click = label, lambda c=command: self._choose(c)
            row = theme.button(body, text, click, fg=fg,
                               anchor="w", padx=12, pady=4, font=theme.FONT,
                               activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT)
            row.pack(fill="x")
            row.bind("<Enter>", lambda _e, i=index: self._activate(i), add="+")
            self._rows.append((row, command))
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x, y = place_menu(x, y, w, h, _work_area(win, x, y), flip_y)
        win.geometry(f"+{x}+{y}")
        win.update_idletasks()
        theme.reveal(win)
        win.bind("<ButtonPress>", self._on_press, add="+")
        win.bind("<Escape>", lambda _e: self.unpost())
        win.bind("<Up>", lambda _e: self._step(-1))
        win.bind("<Down>", lambda _e: self._step(+1))
        win.bind("<Home>", lambda _e: self._activate(0))
        win.bind("<End>", lambda _e: self._activate(len(self._rows) - 1))
        for key in ("<Return>", "<KP_Enter>", "<space>"):
            win.bind(key, lambda _e: self._invoke_active())
        win.bind("<FocusOut>", self._on_focus_out)
        win.focus_force()
        try:
            win.grab_set()
        except tk.TclError:
            pass

    post = tk_popup

    # ---- the highlighted row ---------------------------------------------
    def _activate(self, index):
        """Light row `index` and no other, whichever of the pointer and the
        keyboard put it there."""
        if not self._rows:
            return
        index = max(0, min(index, len(self._rows) - 1))
        if self._active is not None and self._active != index:
            self._rows[self._active][0].set_hover(False)
        self._active = index
        self._rows[index][0].set_hover(True)

    def _step(self, delta):
        if not self._rows:
            return
        if self._active is None:
            self._activate(0 if delta > 0 else len(self._rows) - 1)
        else:
            self._activate((self._active + delta) % len(self._rows))

    def _invoke_active(self):
        if self._active is None:
            return
        if self._active in self._ticks:
            self._toggle(self._active)
        else:
            self._choose(self._rows[self._active][1])

    def _toggle(self, index):
        """A tick row: run it and keep the menu, every tick re-read - one
        click can change several (ALL, or a label that turns into ALL)."""
        command = self._rows[index][1]
        if command is not None:
            command()
        if self._win is None:
            return  # the command closed the menu itself
        for i, (label, checked) in self._ticks.items():
            self._rows[i][0].configure(text=self._tick_text(label, checked()))

    # ---- closing ---------------------------------------------------------
    def _inside(self, event):
        win = self._win
        return (win.winfo_rootx() <= event.x_root < win.winfo_rootx() + win.winfo_width()
                and win.winfo_rooty() <= event.y_root < win.winfo_rooty() + win.winfo_height())

    def _on_press(self, event):
        if self._win is not None and not self._inside(event):
            self.unpost()

    def _on_focus_out(self, _event):
        # Focus moving between our own rows is not leaving the menu.
        win = self._win
        if win is not None:
            win.after(50, lambda: self._win is win and win.focus_get() is None and self.unpost())

    def _choose(self, command):
        self.unpost()
        if command is not None:
            command()

    def unpost(self):
        win, self._win = self._win, None
        self._rows, self._ticks, self._active = [], {}, None
        if win is not None:
            try:
                win.grab_release()
                win.destroy()
            except tk.TclError:
                pass
            if self._on_close is not None:
                self._on_close()


class Dialog(tk.Toplevel):
    """A modal window in the kit's colours, centred on the kit."""

    def __init__(self, parent, title=TITLE):
        parent = _root(parent)
        super().__init__(parent, bg=theme.BG)
        theme.unseen(self)      # shown by `run`, once it stands where it belongs
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        theme.dark_title_bar(self)
        self.result = None
        self.body = theme.frame(self)
        self.body.pack(padx=16, pady=12, fill="both", expand=True)
        tk.Frame(self.body, bg=theme.BG, width=DIALOG_MIN_W, height=0).pack()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        self._parent = parent

    def buttons(self, *specs):
        """`(text, command, primary)` from right to left."""
        row = theme.frame(self.body)
        row.pack(fill="x", pady=(12, 0))
        for i, (text, command, primary) in enumerate(specs):
            kw = dict(bg=theme.WORK, fg=theme.ON_ACCENT, activebackground=theme.ACCENT,
                      activeforeground=theme.ON_ACCENT) if primary else {}
            theme.button(row, text, command, padx=12, **kw).pack(
                side="right", padx=(0 if i == 0 else 6, 0))
        return row

    def run(self, focus=None):
        self.update_idletasks()
        p = self._parent.winfo_toplevel()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = p.winfo_rootx() + max(0, (p.winfo_width() - w) // 2)
        y = p.winfo_rooty() + max(0, (p.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")
        self.update_idletasks()
        theme.reveal(self)
        (focus or self).focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()
        return self.result

    def finish(self, value):
        self.result = value
        self.destroy()

    def cancel(self):
        self.destroy()


def _message(title, message, parent, kind, question=False):
    dlg = Dialog(parent, title)
    row = theme.frame(dlg.body)
    row.pack(fill="x", anchor="w")
    tk.Frame(row, bg=KIND_COLOURS.get(kind, theme.ACCENT), width=3).pack(
        side="left", fill="y", padx=(0, 10))
    theme.label(row, message, justify="left", anchor="w", wraplength=420).pack(
        side="left", anchor="w")
    if question:
        dlg.result = False
        dlg.buttons((t("no"), lambda: dlg.finish(False), False),
                    (t("yes"), lambda: dlg.finish(True), True))
    else:
        dlg.buttons((t("ok"), lambda: dlg.finish(True), True))
    dlg.bind("<Return>", lambda e: dlg.finish(True))
    return dlg.run()


def showinfo(title=TITLE, message="", parent=None, **_kw):
    _message(title, message, parent, "info")


def showwarning(title=TITLE, message="", parent=None, **_kw):
    _message(title, message, parent, "warning")


def showerror(title=TITLE, message="", parent=None, **_kw):
    _message(title, message, parent, "error")


def askyesno(title=TITLE, message="", parent=None, icon="info", **_kw):
    """`icon` as `messagebox` takes it: "warning" or "error" colours the
    strip for a question with a cost, like deleting a drawing."""
    return bool(_message(title, message, parent, icon, question=True))


def askstring(title=TITLE, prompt="", initialvalue="", parent=None, **_kw):
    """One line of text, or None if cancelled."""
    dlg = Dialog(parent, title)
    theme.label(dlg.body, prompt, font=theme.FONT_BOLD).pack(anchor="w", pady=(0, 6))
    entry = theme.entry(dlg.body, width=28)
    entry.insert(0, initialvalue or "")
    entry.select_range(0, "end")
    entry.pack(fill="x", ipady=3)
    dlg.buttons((t("cancel"), dlg.cancel, False),
                (t("ok"), lambda: dlg.finish(entry.get()), True))
    dlg.bind("<Return>", lambda e: dlg.finish(entry.get()))
    return dlg.run(focus=entry)
