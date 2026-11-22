#!/usr/bin/env python3
"""
Lightweight Cross-Platform Proxy Connectivity Tester (Python Tkinter).
Supports Windows, macOS, and Linux with zero third-party dependencies.
"""

from __future__ import annotations

import queue
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox, simpledialog
from typing import Callable, Dict, List, Optional

from proxy_core import (
    DEFAULT_TEST_HOST,
    DEFAULT_TEST_PORT,
    IP_SOURCES,
    PROTOCOLS,
    IpCheckResult,
    ProxyEntry,
    check_ip_source,
    detect_system_proxies,
    load_config,
    parse_proxy_uri,
    save_config,
    test_proxy,
)
from ui_widgets import (
    THEME,
    FlatTextButton,
    ScrollableFrame,
    TelegramRadioRow,
    UnderlineEntry,
    enable_dpi_awareness,
    get_ui_font,
)


class EditProxyDialog(tk.Toplevel):
    """Modal dialog matching the '编辑代理' reference screen."""

    def __init__(
        self,
        master: tk.Misc,
        entry: Optional[ProxyEntry] = None,
        on_save: Optional[Callable[[ProxyEntry], None]] = None,
    ) -> None:
        super().__init__(master)
        self._entry = entry
        self._on_save = on_save
        self._selected_proto = entry.protocol if entry else "SOCKS5"
        self._proto_rows: Dict[str, TelegramRadioRow] = {}

        self.title("编辑代理" if entry else "添加代理")
        self.configure(bg=THEME["bg"])
        self.minsize(360, 500)
        self.transient(master)
        self.grab_set()

        w, h = 370, 540
        x = master.winfo_rootx() + max(0, (master.winfo_width() - w) // 2)
        y = master.winfo_rooty() + max(0, (master.winfo_height() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()
        self._refresh_protocol_view()

    def _build_ui(self) -> None:
        root = tk.Frame(self, bg=THEME["bg"], padx=22, pady=18)
        root.pack(fill="both", expand=True)

        tk.Label(
            root,
            text="编辑代理" if self._entry else "添加代理",
            font=get_ui_font(12, "bold"),
            fg=THEME["text"],
            bg=THEME["bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        for proto in PROTOCOLS:
            row = TelegramRadioRow(
                root,
                text=proto,
                selected=(proto == self._selected_proto),
                on_click=lambda p=proto: self._select_protocol(p),
            )
            row.pack(fill="x", pady=2)
            self._proto_rows[proto] = row

        self.desc_label = tk.Label(
            root,
            text="",
            font=get_ui_font(9),
            fg=THEME["muted"],
            bg=THEME["bg"],
            justify="left",
            wraplength=310,
            anchor="w",
        )
        self.desc_label.pack(fill="x", pady=(10, 14))

        tk.Label(
            root,
            text="代理地址",
            font=get_ui_font(10, "bold"),
            fg=THEME["text"],
            bg=THEME["bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        addr_row = tk.Frame(root, bg=THEME["bg"])
        addr_row.pack(fill="x", pady=(0, 16))

        self.host_input = UnderlineEntry(
            addr_row,
            caption="服务器",
            initial_value=self._entry.host if self._entry else "",
        )
        self.host_input.pack(side="left", fill="x", expand=True, padx=(0, 14))

        self.port_input = UnderlineEntry(
            addr_row,
            caption="端口",
            initial_value=str(self._entry.port) if self._entry else "",
            width=76,
        )
        self.port_input.pack(side="right")
        self.port_input.pack_propagate(False)

        tk.Label(
            root,
            text="认证信息",
            font=get_ui_font(10, "bold"),
            fg=THEME["text"],
            bg=THEME["bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        footer = tk.Frame(root, bg=THEME["bg"])
        footer.pack(side="bottom", fill="x", pady=(14, 0))

        FlatTextButton(footer, text="保存", command=self._save).pack(side="right")
        FlatTextButton(footer, text="取消", command=self.destroy).pack(side="right", padx=(0, 4))

        self.auth_container = tk.Frame(root, bg=THEME["bg"])
        self.auth_container.pack(fill="both", expand=True)

        self.secret_input = UnderlineEntry(
            self.auth_container,
            caption="密钥",
            initial_value=self._entry.secret if self._entry else "",
        )
        self.user_input = UnderlineEntry(
            self.auth_container,
            caption="用户名 (可选)",
            initial_value=self._entry.username if self._entry else "",
        )
        self.pass_input = UnderlineEntry(
            self.auth_container,
            caption="密码 (可选)",
            initial_value=self._entry.password if self._entry else "",
            show="*",
        )

        self.host_input.entry.focus_set()

    def _select_protocol(self, proto: str) -> None:
        self._selected_proto = proto
        for k, row in self._proto_rows.items():
            row.set_selected(k == proto)
        self._refresh_protocol_view()

    def _refresh_protocol_view(self) -> None:
        for child in self.auth_container.winfo_children():
            child.pack_forget()

        if self._selected_proto == "MTPROTO":
            self.desc_label.configure(
                text="该代理支持 MTProto 握手与密钥格式校验，仅测试 TCP 连通性与端口延迟。"
            )
            self.secret_input.pack(fill="x", pady=(0, 8))
        else:
            self.desc_label.configure(
                text="将通过标准协议握手并访问探测目标测量端到端往返延迟（毫秒）。"
            )
            self.user_input.pack(fill="x", pady=(0, 10))
            self.pass_input.pack(fill="x", pady=(0, 8))

    def _save(self) -> None:
        host = self.host_input.get()
        port_raw = self.port_input.get()
        if not host:
            messagebox.showwarning("输入校验", "请输入代理服务器地址。", parent=self)
            return
        if not port_raw.isdigit() or not (1 <= int(port_raw) <= 65535):
            messagebox.showwarning("输入校验", "请输入有效端口号 (1 - 65535)。", parent=self)
            return

        updated = ProxyEntry(
            id=self._entry.id if self._entry else f"p_{int(time.time() * 1000)}",
            protocol=self._selected_proto,
            host=host,
            port=int(port_raw),
            secret=self.secret_input.get() if self._selected_proto == "MTPROTO" else "",
            username="" if self._selected_proto == "MTPROTO" else self.user_input.get(),
            password="" if self._selected_proto == "MTPROTO" else self.pass_input.get(),
            status="testing",
        )
        if self._on_save:
            self._on_save(updated)
        self.destroy()


class ProxyRowWidget(tk.Frame):
    """Single proxy entry row matching the '代理设置' list item layout."""

    def __init__(
        self,
        master: tk.Misc,
        entry: ProxyEntry,
        selected: bool,
        on_select: Callable[[str], None],
        on_test: Callable[[str], None],
        on_edit: Callable[[str], None],
        on_delete: Callable[[str], None],
        on_copy: Callable[[str], None],
    ) -> None:
        super().__init__(master, bg=THEME["bg"], cursor="hand2")
        self.entry = entry
        self._on_select = on_select

        self.radio = tk.Canvas(
            self, width=26, height=26, bg=THEME["bg"], highlightthickness=0, bd=0
        )
        self.radio.pack(side="left", padx=(20, 12), pady=10)

        text_box = tk.Frame(self, bg=THEME["bg"])
        text_box.pack(side="left", fill="x", expand=True, pady=8)

        line1 = tk.Frame(text_box, bg=THEME["bg"])
        line1.pack(fill="x")

        self.proto_lbl = tk.Label(
            line1,
            text=entry.protocol,
            font=get_ui_font(10, "bold"),
            fg=THEME["text"],
            bg=THEME["bg"],
        )
        self.proto_lbl.pack(side="left")

        self.addr_lbl = tk.Label(
            line1,
            text=f" {entry.address_label()}",
            font=get_ui_font(10),
            fg=THEME["muted"],
            bg=THEME["bg"],
        )
        self.addr_lbl.pack(side="left")

        self.status_lbl = tk.Label(
            text_box,
            text="",
            font=get_ui_font(9),
            fg=THEME["muted"],
            bg=THEME["bg"],
            anchor="w",
        )
        self.status_lbl.pack(fill="x")

        self.menu_btn = tk.Label(
            self,
            text="⋮",
            font=get_ui_font(13, "bold"),
            fg=THEME["muted"],
            bg=THEME["bg"],
            padx=14,
            pady=10,
            cursor="hand2",
        )
        self.menu_btn.pack(side="right")

        self._menu = tk.Menu(
            self,
            tearoff=0,
            bg=THEME["bg_menu"],
            fg=THEME["text"],
            activebackground=THEME["accent"],
            activeforeground=THEME["text"],
            bd=0,
        )
        self._menu.add_command(label="立即测试", command=lambda: on_test(self.entry.id))
        self._menu.add_command(label="编辑代理", command=lambda: on_edit(self.entry.id))
        self._menu.add_command(label="复制代理链接", command=lambda: on_copy(self.entry.id))
        self._menu.add_separator()
        self._menu.add_command(label="删除", command=lambda: on_delete(self.entry.id))

        self.menu_btn.bind("<Button-1>", self._show_menu)

        for widget in (self, self.radio, text_box, line1, self.proto_lbl, self.addr_lbl, self.status_lbl):
            widget.bind("<Button-1>", lambda _e: self._on_select(self.entry.id))

        self.update_state(entry, selected)

    def _show_menu(self, event: tk.Event) -> None:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def update_state(self, entry: ProxyEntry, selected: bool) -> None:
        self.entry = entry
        self.proto_lbl.configure(text=entry.protocol)
        self.addr_lbl.configure(text=f" {entry.address_label()}")

        self.radio.delete("all")
        if selected:
            self.radio.create_oval(4, 4, 22, 22, outline=THEME["accent_bright"], width=2)
            self.radio.create_oval(8, 8, 18, 18, fill=THEME["accent_bright"], outline="")
        else:
            self.radio.create_oval(4, 4, 22, 22, outline=THEME["radio_off"], width=2)

        if entry.status == "available" and entry.latency_ms is not None:
            self.status_lbl.configure(
                text=f"可用 (ping: {entry.latency_ms} 毫秒)",
                fg=THEME["ok"],
            )
        elif entry.status == "testing":
            self.status_lbl.configure(text="正在测试连通性...", fg=THEME["accent_bright"])
        elif entry.status == "unavailable":
            reason = f" · {entry.detail}" if entry.detail else ""
            self.status_lbl.configure(text=f"不可用{reason}", fg=THEME["err"])
        else:
            self.status_lbl.configure(text="未测试", fg=THEME["muted"])


class ProxyTesterApp:
    """Main lightweight Tkinter application matching the '代理设置' screen."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ProxyPing · 代理设置与多源出口 IP 检测")
        self.root.configure(bg=THEME["bg"])
        self.root.geometry("940x640")
        self.root.minsize(820, 540)

        cfg = load_config()
        self.mode: str = cfg.get("mode", "system")
        self.selected_id: Optional[str] = cfg.get("selected_id")
        self.target_host: str = cfg.get("target_host", DEFAULT_TEST_HOST)
        self.target_port: int = int(cfg.get("target_port", DEFAULT_TEST_PORT))
        self.proxies: List[ProxyEntry] = [ProxyEntry(**p) for p in cfg.get("proxies", [])]
        self.system_proxies: List[tuple] = []
        self.ip_route_mode: str = "direct"  # direct | proxy

        self._executor = ThreadPoolExecutor(max_workers=8)
        self._result_queue: queue.Queue = queue.Queue()
        self._ip_queue: queue.Queue = queue.Queue()
        self._proxy_widgets: Dict[str, ProxyRowWidget] = {}
        self._ip_cards: Dict[str, Dict[str, tk.Label]] = {}

        self._build_ui()
        self._refresh_system_proxy()
        self._render_proxy_list()
        self.test_all_proxies()
        self.test_all_ip_sources()
        self.root.after(60, self._poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        shell = tk.Frame(self.root, bg=THEME["bg"])
        shell.pack(fill="both", expand=True)

        left_pane = tk.Frame(shell, bg=THEME["bg"], width=390)
        left_pane.pack(side="left", fill="y")
        left_pane.pack_propagate(False)

        tk.Frame(shell, bg=THEME["border"], width=1).pack(side="left", fill="y")

        right_pane = tk.Frame(shell, bg=THEME["bg_recessed"])
        right_pane.pack(side="left", fill="both", expand=True)

        # Top Header (Left Pane)
        header = tk.Frame(left_pane, bg=THEME["bg"], padx=20, pady=14)
        header.pack(fill="x")

        tk.Label(
            header,
            text="代理设置",
            font=get_ui_font(12, "bold"),
            fg=THEME["text"],
            bg=THEME["bg"],
        ).pack(side="left")

        self.global_menu_btn = tk.Label(
            header,
            text="⋮",
            font=get_ui_font(14, "bold"),
            fg=THEME["muted"],
            bg=THEME["bg"],
            padx=8,
            cursor="hand2",
        )
        self.global_menu_btn.pack(side="right")

        self._global_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=THEME["bg_menu"],
            fg=THEME["text"],
            activebackground=THEME["accent"],
            activeforeground=THEME["text"],
            bd=0,
        )
        self._global_menu.add_command(label="全部重新测试", command=self.test_all_proxies)
        self._global_menu.add_command(label="检测系统代理", command=self._refresh_system_proxy)
        self._global_menu.add_command(label="导入代理链接", command=self._import_proxy_uri)
        self._global_menu.add_command(label="设置探测目标", command=self._configure_target)
        self._global_menu.add_separator()
        self._global_menu.add_command(label="清空不可用代理", command=self._clear_unavailable)

        self.global_menu_btn.bind("<Button-1>", self._show_global_menu)

        # Recessed Notice Band
        notice = tk.Frame(left_pane, bg=THEME["bg_recessed"], padx=20, pady=12)
        notice.pack(fill="x")

        self.notice_label = tk.Label(
            notice,
            text=(
                "代理服务器可能有助于解决个别地区无法连接目标网络的情况。\n"
                f"当前探测目标: {self.target_host}:{self.target_port}"
            ),
            font=get_ui_font(9),
            fg=THEME["muted"],
            bg=THEME["bg_recessed"],
            justify="left",
            anchor="w",
        )
        self.notice_label.pack(fill="x")

        # Pack Footer BEFORE expandable list so Add/Test/Close buttons are never clipped
        footer = tk.Frame(left_pane, bg=THEME["bg"], padx=16, pady=12)
        footer.pack(side="bottom", fill="x")

        self.status_hint = tk.Label(
            footer,
            text="",
            font=get_ui_font(9),
            fg=THEME["muted"],
            bg=THEME["bg"],
        )
        self.status_hint.pack(side="left", padx=(4, 0))

        FlatTextButton(footer, text="添加", command=self._open_add_dialog).pack(side="right")
        FlatTextButton(footer, text="全部测试", command=self.test_all_proxies).pack(side="right")
        FlatTextButton(footer, text="关闭", command=self._on_close).pack(side="right")

        # Scrollable Proxy List fills remaining vertical space
        self.list_container = ScrollableFrame(left_pane, bg=THEME["bg"])
        self.list_container.pack(side="top", fill="both", expand=True, pady=(6, 0))

        # Right Pane: IP233-style Multi-Source IP Exit Check
        ip_header = tk.Frame(right_pane, bg=THEME["bg_recessed"], padx=20, pady=14)
        ip_header.pack(fill="x")

        tk.Label(
            ip_header,
            text="多源出口 IP 检测",
            font=get_ui_font(12, "bold"),
            fg=THEME["text"],
            bg=THEME["bg_recessed"],
        ).pack(side="left")

        FlatTextButton(
            ip_header,
            text="刷新全部源",
            command=self.test_all_ip_sources,
            bg=THEME["bg_recessed"],
        ).pack(side="right")

        route_bar = tk.Frame(right_pane, bg=THEME["bg"], padx=20, pady=10)
        route_bar.pack(fill="x")

        self.route_direct_btn = FlatTextButton(
            route_bar,
            text="本机直连探测",
            command=lambda: self._set_ip_route("direct"),
            fg=THEME["accent_bright"],
            bg=THEME["bg"],
        )
        self.route_direct_btn.pack(side="left")

        self.route_proxy_btn = FlatTextButton(
            route_bar,
            text="通过选中代理探测",
            command=lambda: self._set_ip_route("proxy"),
            fg=THEME["muted"],
            bg=THEME["bg"],
        )
        self.route_proxy_btn.pack(side="left")

        self.ip_list_frame = ScrollableFrame(right_pane, bg=THEME["bg_recessed"])
        self.ip_list_frame.pack(fill="both", expand=True, padx=16, pady=(10, 16))

        for src in IP_SOURCES:
            card = tk.Frame(
                self.ip_list_frame.inner,
                bg=THEME["bg"],
                padx=14,
                pady=10,
                highlightbackground=THEME["border"],
                highlightthickness=1,
            )
            card.pack(fill="x", pady=4)

            top_row = tk.Frame(card, bg=THEME["bg"])
            top_row.pack(fill="x")

            tk.Label(
                top_row,
                text=f"{src['name']}  ·  {src['region']}",
                font=get_ui_font(9),
                fg=THEME["muted"],
                bg=THEME["bg"],
            ).pack(side="left")

            lat_lbl = tk.Label(
                top_row,
                text="等待检测",
                font=get_ui_font(9),
                fg=THEME["muted"],
                bg=THEME["bg"],
            )
            lat_lbl.pack(side="right")

            ip_lbl = tk.Label(
                card,
                text="—",
                font=get_ui_font(12, "bold"),
                fg=THEME["text"],
                bg=THEME["bg"],
                anchor="w",
            )
            ip_lbl.pack(fill="x", pady=(4, 2))

            meta_lbl = tk.Label(
                card,
                text="点击「刷新全部源」发起探测",
                font=get_ui_font(9),
                fg=THEME["muted"],
                bg=THEME["bg"],
                anchor="w",
            )
            meta_lbl.pack(fill="x")

            self._ip_cards[src["id"]] = {
                "lat": lat_lbl,
                "ip": ip_lbl,
                "meta": meta_lbl,
            }

    def _show_global_menu(self, event: tk.Event) -> None:
        try:
            self._global_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._global_menu.grab_release()

    def _refresh_system_proxy(self) -> None:
        self.system_proxies = detect_system_proxies()
        self._refresh_notice_text()

    def _refresh_notice_text(self) -> None:
        sys_info = (
            ", ".join(f"{p} {h}:{pt}" for p, h, pt in self.system_proxies)
            if self.system_proxies
            else "未检测到系统代理"
        )
        self.notice_label.configure(
            text=(
                "代理服务器可能有助于解决个别地区无法连接目标网络的情况。\n"
                f"探测目标: {self.target_host}:{self.target_port} · 系统代理: {sys_info}"
            )
        )

    def _render_proxy_list(self) -> None:
        for child in self.list_container.inner.winfo_children():
            child.destroy()
        self._proxy_widgets.clear()

        if not self.proxies:
            tk.Label(
                self.list_container.inner,
                text="暂无代理配置，点击右下角「添加」创建代理。",
                font=get_ui_font(9),
                fg=THEME["muted"],
                bg=THEME["bg"],
                pady=32,
            ).pack(fill="x")
            return

        for entry in self.proxies:
            widget = ProxyRowWidget(
                self.list_container.inner,
                entry=entry,
                selected=(entry.id == self.selected_id),
                on_select=self._select_proxy,
                on_test=self.test_single_proxy,
                on_edit=self._open_edit_dialog,
                on_delete=self._delete_proxy,
                on_copy=self._copy_single_proxy,
            )
            widget.pack(fill="x")
            self._proxy_widgets[entry.id] = widget

    def _select_proxy(self, proxy_id: str) -> None:
        self.selected_id = proxy_id
        for pid, widget in self._proxy_widgets.items():
            widget.update_state(widget.entry, pid == proxy_id)
        self._persist()

    def _open_add_dialog(self) -> None:
        EditProxyDialog(self.root, entry=None, on_save=self._on_add_saved)

    def _open_edit_dialog(self, proxy_id: str) -> None:
        target = next((p for p in self.proxies if p.id == proxy_id), None)
        if target:
            EditProxyDialog(self.root, entry=target, on_save=self._on_edit_saved)

    def _on_add_saved(self, new_entry: ProxyEntry) -> None:
        self.proxies.append(new_entry)
        self.selected_id = new_entry.id
        self._persist()
        self._render_proxy_list()
        self.test_single_proxy(new_entry.id)

    def _on_edit_saved(self, updated: ProxyEntry) -> None:
        for idx, item in enumerate(self.proxies):
            if item.id == updated.id:
                self.proxies[idx] = updated
                break
        self._persist()
        self._render_proxy_list()
        self.test_single_proxy(updated.id)

    def _delete_proxy(self, proxy_id: str) -> None:
        self.proxies = [p for p in self.proxies if p.id != proxy_id]
        if self.selected_id == proxy_id:
            self.selected_id = self.proxies[0].id if self.proxies else None
        self._persist()
        self._render_proxy_list()

    def _copy_single_proxy(self, proxy_id: str) -> None:
        target = next((p for p in self.proxies if p.id == proxy_id), None)
        if target:
            self.root.clipboard_clear()
            self.root.clipboard_append(target.to_share_uri())
            self._flash_hint("已复制代理链接")

    def _import_proxy_uri(self) -> None:
        raw = simpledialog.askstring(
            "导入代理链接",
            "请输入代理地址 (如 socks5://127.0.0.1:1080 或 tg://proxy?...):",
            parent=self.root,
        )
        if not raw:
            return
        parsed = parse_proxy_uri(raw)
        if not parsed:
            messagebox.showerror("解析失败", "无法识别该代理链接格式。", parent=self.root)
            return
        self._on_add_saved(parsed)

    def _configure_target(self) -> None:
        raw = simpledialog.askstring(
            "设置探测目标",
            "输入目标主机与端口 (host:port):",
            initialvalue=f"{self.target_host}:{self.target_port}",
            parent=self.root,
        )
        if not raw or ":" not in raw:
            return
        host, port_str = raw.rsplit(":", 1)
        if host.strip() and port_str.strip().isdigit():
            self.target_host = host.strip()
            self.target_port = int(port_str.strip())
            self._refresh_notice_text()
            self._persist()
            self.test_all_proxies()

    def _clear_unavailable(self) -> None:
        self.proxies = [p for p in self.proxies if p.status != "unavailable"]
        if self.selected_id and not any(p.id == self.selected_id for p in self.proxies):
            self.selected_id = self.proxies[0].id if self.proxies else None
        self._persist()
        self._render_proxy_list()

    def test_single_proxy(self, proxy_id: str) -> None:
        target = next((p for p in self.proxies if p.id == proxy_id), None)
        if not target:
            return
        target.status = "testing"
        target.latency_ms = None
        target.detail = ""
        if proxy_id in self._proxy_widgets:
            self._proxy_widgets[proxy_id].update_state(target, proxy_id == self.selected_id)

        def worker() -> None:
            res = test_proxy(target, self.target_host, self.target_port)
            self._result_queue.put((proxy_id, res))

        self._executor.submit(worker)

    def test_all_proxies(self) -> None:
        for entry in self.proxies:
            self.test_single_proxy(entry.id)

    def _set_ip_route(self, route_mode: str) -> None:
        self.ip_route_mode = route_mode
        self.route_direct_btn.configure(
            fg=THEME["accent_bright"] if route_mode == "direct" else THEME["muted"]
        )
        self.route_proxy_btn.configure(
            fg=THEME["accent_bright"] if route_mode == "proxy" else THEME["muted"]
        )
        self.test_all_ip_sources()

    def test_all_ip_sources(self) -> None:
        active_proxy: Optional[ProxyEntry] = None
        if self.ip_route_mode == "proxy" and self.selected_id:
            active_proxy = next((p for p in self.proxies if p.id == self.selected_id), None)

        for src in IP_SOURCES:
            widgets = self._ip_cards.get(src["id"])
            if widgets:
                widgets["lat"].configure(text="检测中...", fg=THEME["accent_bright"])
                widgets["ip"].configure(text="正在获取...", fg=THEME["muted"])
                widgets["meta"].configure(text="", fg=THEME["muted"])

            def ip_worker(s=src, p=active_proxy) -> None:
                res = check_ip_source(s, proxy=p)
                self._ip_queue.put(res)

            self._executor.submit(ip_worker)

    def _poll_results(self) -> None:
        try:
            while True:
                proxy_id, res = self._result_queue.get_nowait()
                entry = next((p for p in self.proxies if p.id == proxy_id), None)
                if entry:
                    entry.status = "available" if res.available else "unavailable"
                    entry.latency_ms = res.latency_ms
                    entry.detail = res.detail
                    if proxy_id in self._proxy_widgets:
                        self._proxy_widgets[proxy_id].update_state(
                            entry, proxy_id == self.selected_id
                        )
        except queue.Empty:
            pass

        try:
            while True:
                ip_res: IpCheckResult = self._ip_queue.get_nowait()
                widgets = self._ip_cards.get(ip_res.source_id)
                if widgets:
                    if ip_res.ok:
                        lat_text = f"{ip_res.latency_ms} ms" if ip_res.latency_ms else "可达"
                        widgets["lat"].configure(text=lat_text, fg=THEME["ok"])
                        widgets["ip"].configure(text=ip_res.ip, fg=THEME["text"])
                        meta = "  ·  ".join(x for x in (ip_res.location, ip_res.isp) if x)
                        widgets["meta"].configure(text=meta or "解析完成", fg=THEME["muted"])
                    else:
                        widgets["lat"].configure(text="失败", fg=THEME["err"])
                        widgets["ip"].configure(text="不可达", fg=THEME["err"])
                        widgets["meta"].configure(text=ip_res.error, fg=THEME["muted"])
        except queue.Empty:
            pass

        self.root.after(60, self._poll_results)

    def _flash_hint(self, text: str) -> None:
        self.status_hint.configure(text=text)
        self.root.after(2500, lambda: self.status_hint.configure(text=""))

    def _persist(self) -> None:
        save_config(
            self.mode,
            self.selected_id,
            self.proxies,
            self.target_host,
            self.target_port,
        )

    def _on_close(self) -> None:
        self._persist()
        self._executor.shutdown(wait=False)
        self.root.destroy()


def main() -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    ProxyTesterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
