"""
Lightweight Telegram-style dark UI widgets for Python Tkinter.
Custom Canvas-drawn controls guarantee consistent rendering across
Windows, Linux (X11/Wayland), and macOS.
"""

from __future__ import annotations

import ctypes
import platform
import tkinter as tk
from typing import Callable, Optional


THEME = {
    "bg": "#1e2732",
    "bg_recessed": "#17212b",
    "bg_hover": "#26323e",
    "bg_menu": "#242f3d",
    "border": "#2f3d4c",
    "input_line": "#3b4a59",
    "accent": "#5288c1",
    "accent_bright": "#64b5f6",
    "text": "#f5f5f5",
    "muted": "#7f91a4",
    "ok": "#45b97c",
    "err": "#e05a5a",
    "radio_off": "#6b7c8e",
}


def enable_dpi_awareness() -> None:
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def get_ui_font(size: int = 10, weight: str = "normal") -> tuple:
    sys_name = platform.system()
    if sys_name == "Windows":
        family = "Microsoft YaHei UI"
    elif sys_name == "Darwin":
        family = "PingFang SC"
    else:
        family = "Noto Sans CJK SC"
    return (family, size, weight) if weight != "normal" else (family, size)


class TelegramRadioRow(tk.Frame):
    """Canvas-drawn circular radio row with clean hover & single-click toggle."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        selected: bool = False,
        on_click: Optional[Callable[[], None]] = None,
        bg: str = THEME["bg"],
        **kwargs,
    ) -> None:
        super().__init__(master, bg=bg, cursor="hand2", **kwargs)
        self._bg = bg
        self._selected = selected
        self._on_click = on_click

        self.canvas = tk.Canvas(
            self,
            width=24,
            height=24,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(side="left", padx=(0, 12), pady=4)

        self.label = tk.Label(
            self,
            text=text,
            font=get_ui_font(10),
            fg=THEME["text"],
            bg=bg,
            anchor="w",
            cursor="hand2",
        )
        self.label.pack(side="left", fill="x", expand=True)

        self._draw_radio()

        for widget in (self, self.canvas, self.label):
            widget.bind("<Button-1>", self._handle_click)
            widget.bind("<Enter>", lambda _e: self._set_hover(True))
            widget.bind("<Leave>", lambda _e: self._set_hover(False))

    def _handle_click(self, _event: tk.Event) -> None:
        if self._on_click:
            self._on_click()

    def _set_hover(self, hovering: bool) -> None:
        color = THEME["bg_hover"] if hovering else self._bg
        self.configure(bg=color)
        self.canvas.configure(bg=color)
        self.label.configure(bg=color)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._draw_radio()

    def _draw_radio(self) -> None:
        self.canvas.delete("all")
        if self._selected:
            self.canvas.create_oval(3, 3, 21, 21, outline=THEME["accent_bright"], width=2)
            self.canvas.create_oval(7, 7, 17, 17, fill=THEME["accent_bright"], outline="")
        else:
            self.canvas.create_oval(3, 3, 21, 21, outline=THEME["radio_off"], width=2)


class UnderlineEntry(tk.Frame):
    """Telegram Desktop underline input field with floating-style header caption."""

    def __init__(
        self,
        master: tk.Misc,
        caption: str,
        initial_value: str = "",
        show: str = "",
        bg: str = THEME["bg"],
        **kwargs,
    ) -> None:
        super().__init__(master, bg=bg, **kwargs)
        self._bg = bg

        self.caption_label = tk.Label(
            self,
            text=caption,
            font=get_ui_font(9),
            fg=THEME["muted"],
            bg=bg,
            anchor="w",
        )
        self.caption_label.pack(fill="x", pady=(0, 2))

        self.var = tk.StringVar(value=initial_value)
        self.entry = tk.Entry(
            self,
            textvariable=self.var,
            font=get_ui_font(10),
            fg=THEME["text"],
            bg=bg,
            insertbackground=THEME["accent_bright"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            show=show,
        )
        self.entry.pack(fill="x", ipady=4)

        self.line = tk.Frame(self, height=2, bg=THEME["input_line"])
        self.line.pack(fill="x")

        self.entry.bind("<FocusIn>", lambda _e: self._on_focus(True))
        self.entry.bind("<FocusOut>", lambda _e: self._on_focus(False))

    def _on_focus(self, focused: bool) -> None:
        color = THEME["accent_bright"] if focused else THEME["input_line"]
        caption_color = THEME["accent_bright"] if focused else THEME["muted"]
        self.line.configure(bg=color)
        self.caption_label.configure(fg=caption_color)

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, val: str) -> None:
        self.var.set(val)


class FlatTextButton(tk.Label):
    """Flat borderless Telegram text button with subtle hover fill."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        fg: str = THEME["accent_bright"],
        bg: str = THEME["bg"],
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            text=text,
            font=get_ui_font(10, "bold"),
            fg=fg,
            bg=bg,
            padx=14,
            pady=7,
            cursor="hand2",
            **kwargs,
        )
        self._bg = bg
        self._command = command
        self.bind("<Button-1>", lambda _e: self._command())
        self.bind("<Enter>", lambda _e: self.configure(bg=THEME["bg_hover"]))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._bg))


class ScrollableFrame(tk.Frame):
    """Cross-platform scrollable container (Win/macOS MouseWheel + Linux Button-4/5)."""

    def __init__(self, master: tk.Misc, bg: str = THEME["bg"], **kwargs) -> None:
        super().__init__(master, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=120)
        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            bg=bg,
            troughcolor=bg,
            activebackground=THEME["accent"],
            width=6,
            relief="flat",
            bd=0,
        )
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.inner)

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        widget.bind("<Enter>", lambda _e: self._activate_wheel(), add="+")
        widget.bind("<Leave>", lambda _e: self._deactivate_wheel(), add="+")

    def _activate_wheel(self) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))

    def _deactivate_wheel(self) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if platform.system() == "Darwin":
            delta = -1 * int(event.delta)
        else:
            delta = -1 * int(event.delta / 120)
        if delta != 0:
            self.canvas.yview_scroll(delta, "units")
