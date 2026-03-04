"""
SAS Network Diagnostic Tool — TCP/UDP Socket Tester View
Client/server mode socket testing for industrial connectivity debugging.
"""

import logging
import threading
import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from core.socket_tester import SocketTesterEngine, Protocol, Mode, SocketMessage, ConnectionInfo
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)


class SocketTesterView(ctk.CTkFrame):
    """TCP/UDP Socket Tester — client and server modes."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._engine = SocketTesterEngine()
        self._engine.on_message = self._on_message
        self._engine.on_status = self._on_status
        self._engine.on_error = self._on_error_cb
        self._msg_count = 0
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=24, pady=(16, 8))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🔌  TCP/UDP Socket Tester",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         side="left", fill="x", expand=True)

        # ── Config Row 1: Mode & Protocol ─────────────────────────────────────
        config1 = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        config1.pack(fill="x", padx=24, pady=(0, 4))

        inner1 = ctk.CTkFrame(config1, fg_color="transparent")
        inner1.pack(fill="x", padx=CARD_PADDING, pady=10)

        # Mode selector
        ctk.CTkLabel(inner1, text="Mode:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self._mode_var = ctk.StringVar(value="Client")
        self._mode_seg = ctk.CTkSegmentedButton(
            inner1, values=["Client", "Server"],
            variable=self._mode_var, command=self._on_mode_change,
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            selected_color=SAS_BLUE, selected_hover_color=SAS_BLUE_DARK,
        )
        self._mode_seg.pack(side="left", padx=(0, 20))

        # Protocol selector
        ctk.CTkLabel(inner1, text="Protocol:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))
        self._proto_var = ctk.StringVar(value="TCP")
        self._proto_seg = ctk.CTkSegmentedButton(
            inner1, values=["TCP", "UDP"],
            variable=self._proto_var,
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            selected_color=SAS_BLUE, selected_hover_color=SAS_BLUE_DARK,
        )
        self._proto_seg.pack(side="left", padx=(0, 20))

        # Status indicator
        self._status_label = ctk.CTkLabel(
            inner1, text="⬤ Disconnected",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=STATUS_OFFLINE,
        )
        self._status_label.pack(side="right")

        # ── Config Row 2: Address & Port ──────────────────────────────────────
        config2 = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        config2.pack(fill="x", padx=24, pady=(0, 4))

        inner2 = ctk.CTkFrame(config2, fg_color="transparent")
        inner2.pack(fill="x", padx=CARD_PADDING, pady=10)

        # Host/Bind label (changes based on mode)
        self._addr_label = ctk.CTkLabel(
            inner2, text="Host:", font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_SECONDARY)
        self._addr_label.pack(side="left", padx=(0, 6))

        self._addr_entry = ctk.CTkEntry(
            inner2, width=200, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="192.168.1.1",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        self._addr_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner2, text="Port:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._port_entry = ctk.CTkEntry(
            inner2, width=100, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="44818",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        self._port_entry.pack(side="left", padx=(0, 16))

        # Connect/Disconnect button
        self._connect_btn = ctk.CTkButton(
            inner2, text="Connect", width=120, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            command=self._toggle_connection,
        )
        self._connect_btn.pack(side="left", padx=(0, 8))

        # Clear button
        ctk.CTkButton(
            inner2, text="Clear Log", width=90, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color=BG_CARD_HOVER, hover_color=BORDER_COLOR,
            text_color=TEXT_SECONDARY,
            command=self._clear_log,
        ).pack(side="right")

        # ── Message Log ──────────────────────────────────────────────────────
        log_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 4))

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=CARD_PADDING, pady=(10, 4))
        ctk.CTkLabel(log_header, text="Message Log",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        self._msg_count_label = ctk.CTkLabel(
            log_header, text="0 messages",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED)
        self._msg_count_label.pack(side="right")

        # Log text widget
        self._log_text = tk.Text(
            log_frame, wrap="none", state="disabled",
            font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
            bg=resolve_color(BG_INPUT),
            fg=resolve_color(TEXT_PRIMARY),
            insertbackground=resolve_color(TEXT_PRIMARY),
            selectbackground=resolve_color(SAS_BLUE),
            relief="flat", padx=8, pady=8,
            borderwidth=0,
        )
        self._log_text.pack(fill="both", expand=True, padx=CARD_PADDING, pady=(0, 4))

        # Scrollbar
        log_scroll = ctk.CTkScrollbar(log_frame, command=self._log_text.yview)
        log_scroll.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self._log_text.configure(yscrollcommand=log_scroll.set)

        # Tag colors
        self._log_text.tag_configure("tx", foreground="#22C55E")
        self._log_text.tag_configure("rx", foreground="#3B82F6")
        self._log_text.tag_configure("system", foreground=resolve_color(TEXT_MUTED))
        self._log_text.tag_configure("error", foreground="#EF4444")
        self._log_text.tag_configure("timestamp", foreground=resolve_color(TEXT_MUTED))

        # ── Send Bar ─────────────────────────────────────────────────────────
        send_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        send_frame.pack(fill="x", padx=24, pady=(0, 16))

        send_inner = ctk.CTkFrame(send_frame, fg_color="transparent")
        send_inner.pack(fill="x", padx=CARD_PADDING, pady=10)

        # Format selector
        self._format_var = ctk.StringVar(value="ASCII")
        ctk.CTkSegmentedButton(
            send_inner, values=["ASCII", "Hex"],
            variable=self._format_var,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            selected_color=SAS_BLUE, selected_hover_color=SAS_BLUE_DARK,
            width=120,
        ).pack(side="left", padx=(0, 8))

        self._send_entry = ctk.CTkEntry(
            send_inner, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="Type message or hex bytes (e.g. 48 65 6C 6C 6F)...",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        self._send_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._send_entry.bind("<Return>", lambda e: self._send_data())

        self._send_btn = ctk.CTkButton(
            send_inner, text="Send", width=80, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_ORANGE, hover_color=SAS_ORANGE_DARK,
            command=self._send_data,
        )
        self._send_btn.pack(side="right")

    def _on_mode_change(self, value):
        if value == "Server":
            self._addr_label.configure(text="Bind:")
            self._addr_entry.configure(placeholder_text="0.0.0.0")
            self._connect_btn.configure(text="Start Server")
        else:
            self._addr_label.configure(text="Host:")
            self._addr_entry.configure(placeholder_text="192.168.1.1")
            self._connect_btn.configure(text="Connect")

    def _toggle_connection(self):
        if self._engine.is_running:
            self._engine.disconnect()
            return

        addr = self._addr_entry.get().strip()
        port_str = self._port_entry.get().strip()

        if not port_str:
            self._log_system("Please enter a port number.")
            return

        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            self._log_system("Invalid port number (1-65535).")
            return

        proto = Protocol.TCP if self._proto_var.get() == "TCP" else Protocol.UDP
        mode = self._mode_var.get()

        if mode == "Client":
            if not addr:
                self._log_system("Please enter a host address.")
                return
            self._log_system(f"Connecting to {addr}:{port} ({proto.value})...")
            self._engine.connect_client(addr, port, proto)
        else:
            bind = addr or "0.0.0.0"
            self._log_system(f"Starting {proto.value} server on {bind}:{port}...")
            self._engine.start_server(bind, port, proto)

    def _send_data(self):
        text = self._send_entry.get().strip()
        if not text:
            return

        if self._format_var.get() == "Hex":
            try:
                data = bytes.fromhex(text.replace(" ", ""))
            except ValueError:
                self._log_system("Invalid hex format. Use space-separated bytes: 48 65 6C 6C 6F")
                return
        else:
            data = text.encode("utf-8")

        if self._engine.send(data):
            self._send_entry.delete(0, "end")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._msg_count = 0
        self._msg_count_label.configure(text="0 messages")

    # ── Callbacks (called from background threads) ────────────────────────────

    def _on_message(self, msg: SocketMessage):
        self.after(0, lambda: self._display_message(msg))

    def _on_status(self, info: ConnectionInfo):
        self.after(0, lambda: self._update_status(info))

    def _on_error_cb(self, error: str):
        self.after(0, lambda: self._log_error(error))

    # ── UI Updates (main thread) ─────────────────────────────────────────────

    def _display_message(self, msg: SocketMessage):
        ts = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
        direction = msg.direction
        tag = "tx" if direction == "TX" else "rx"
        arrow = "→" if direction == "TX" else "←"
        remote = f"{msg.remote_addr}:{msg.remote_port}" if msg.remote_addr else ""

        self._log_text.configure(state="normal")

        self._log_text.insert("end", f"[{ts}] ", "timestamp")
        self._log_text.insert("end", f"{direction} {arrow} ", tag)
        if remote:
            self._log_text.insert("end", f"{remote}  ", "system")
        self._log_text.insert("end", f"({msg.size} bytes)\n", "system")

        # Show ASCII
        self._log_text.insert("end", f"  ASCII: {msg.ascii_str}\n", tag)
        # Show Hex
        self._log_text.insert("end", f"  Hex:   {msg.hex_str}\n\n", tag)

        self._log_text.configure(state="disabled")
        self._log_text.see("end")

        self._msg_count += 1
        self._msg_count_label.configure(text=f"{self._msg_count} messages")

    def _update_status(self, info: ConnectionInfo):
        if info.connected:
            mode_str = info.mode.value
            proto_str = info.protocol.value
            if info.mode == Mode.SERVER:
                clients = f" ({info.client_count} clients)" if info.client_count else ""
                self._status_label.configure(
                    text=f"⬤ Listening{clients}",
                    text_color=STATUS_GOOD)
                self._connect_btn.configure(text="Stop Server",
                                           fg_color=STATUS_ERROR,
                                           hover_color="#DC2626")
            else:
                self._status_label.configure(
                    text=f"⬤ Connected ({proto_str})",
                    text_color=STATUS_GOOD)
                self._connect_btn.configure(text="Disconnect",
                                           fg_color=STATUS_ERROR,
                                           hover_color="#DC2626")

            self._log_system(
                f"Connected — {mode_str} {proto_str} "
                f"Local: {info.local_addr}:{info.local_port}"
            )
        else:
            self._status_label.configure(text="⬤ Disconnected",
                                        text_color=STATUS_OFFLINE)
            mode = self._mode_var.get()
            self._connect_btn.configure(
                text="Start Server" if mode == "Server" else "Connect",
                fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            )
            if info.error:
                self._log_error(info.error)
            else:
                self._log_system("Disconnected.")

    def _log_system(self, text: str):
        self._log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] {text}\n", "system")
        self._log_text.configure(state="disabled")
        self._log_text.see("end")

    def _log_error(self, text: str):
        self._log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] ERROR: {text}\n", "error")
        self._log_text.configure(state="disabled")
        self._log_text.see("end")

    def on_show(self):
        """Called when view becomes visible."""
        pass
