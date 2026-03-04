"""
SAS Network Diagnostic Tool — DHCP Server View
Turn the laptop into a DHCP server with on/off toggle, pool config, and lease table.
"""

import logging
import tkinter as tk
from datetime import datetime
from typing import Optional, Dict

import customtkinter as ctk

from core.dhcp_server import DHCPServer, DHCPServerConfig, DHCPLease, DHCPServerStatus
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)


class DHCPServerView(ctk.CTkFrame):
    """DHCP Server — laptop acts as a DHCP server with on/off switch."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._server = DHCPServer()
        self._server.on_lease_change = self._on_lease_change
        self._server.on_status = self._on_status_cb
        self._server.on_error = self._on_error
        self._lease_rows: Dict[str, ctk.CTkFrame] = {}
        self._refresh_timer = None
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=24, pady=(16, 8))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🌐  DHCP Server",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         side="left", fill="x", expand=True)

        # ON/OFF switch
        switch_frame = ctk.CTkFrame(header, fg_color="transparent")
        switch_frame.pack(side="right")

        self._switch_label = ctk.CTkLabel(
            switch_frame, text="OFF",
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            text_color=STATUS_ERROR)
        self._switch_label.pack(side="left", padx=(0, 8))

        self._switch = ctk.CTkSwitch(
            switch_frame, text="",
            onvalue=True, offvalue=False,
            command=self._toggle_server,
            progress_color=SAS_BLUE,
            button_color=SAS_BLUE_LIGHT,
            fg_color=BORDER_COLOR,
            width=50,
        )
        self._switch.pack(side="left")

        # ── Configuration Card ────────────────────────────────────────────────
        config_card = ctk.CTkFrame(self, fg_color=BG_CARD,
                                   corner_radius=CARD_CORNER_RADIUS)
        config_card.pack(fill="x", padx=24, pady=(0, 4))

        ctk.CTkLabel(config_card, text="Server Configuration",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         fill="x", padx=CARD_PADDING, pady=(10, 4))

        # Row 1: Pool range
        row1 = ctk.CTkFrame(config_card, fg_color="transparent")
        row1.pack(fill="x", padx=CARD_PADDING, pady=(0, 4))

        ctk.CTkLabel(row1, text="Pool Start:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY, width=90).pack(side="left")
        self._pool_start = ctk.CTkEntry(
            row1, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR)
        self._pool_start.pack(side="left", padx=(0, 16))
        self._pool_start.insert(0, "192.168.1.100")

        ctk.CTkLabel(row1, text="Pool End:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY, width=80).pack(side="left")
        self._pool_end = ctk.CTkEntry(
            row1, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR)
        self._pool_end.pack(side="left", padx=(0, 16))
        self._pool_end.insert(0, "192.168.1.200")

        ctk.CTkLabel(row1, text="Lease Time (s):", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self._lease_time = ctk.CTkEntry(
            row1, width=80, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR)
        self._lease_time.pack(side="left")
        self._lease_time.insert(0, "3600")

        # Row 2: Network config
        row2 = ctk.CTkFrame(config_card, fg_color="transparent")
        row2.pack(fill="x", padx=CARD_PADDING, pady=(0, 10))

        ctk.CTkLabel(row2, text="Subnet Mask:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY, width=90).pack(side="left")
        self._subnet_mask = ctk.CTkEntry(
            row2, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR)
        self._subnet_mask.pack(side="left", padx=(0, 16))
        self._subnet_mask.insert(0, "255.255.255.0")

        ctk.CTkLabel(row2, text="Gateway:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY, width=80).pack(side="left")
        self._gateway = ctk.CTkEntry(
            row2, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="(optional)",
            fg_color=BG_INPUT, border_color=BORDER_COLOR)
        self._gateway.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row2, text="DNS:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        self._dns = ctk.CTkEntry(
            row2, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="(optional)",
            fg_color=BG_INPUT, border_color=BORDER_COLOR)
        self._dns.pack(side="left")

        # Admin note
        ctk.CTkLabel(config_card,
                     text="⚠  Requires Run as Administrator  •  Only use on isolated networks",
                     font=(FONT_FAMILY, FONT_SIZE_TINY),
                     text_color=STATUS_WARN, anchor="w").pack(
                         fill="x", padx=CARD_PADDING, pady=(0, 10))

        # ── Status Bar ────────────────────────────────────────────────────────
        status_card = ctk.CTkFrame(self, fg_color=BG_CARD,
                                   corner_radius=CARD_CORNER_RADIUS)
        status_card.pack(fill="x", padx=24, pady=(0, 4))

        status_inner = ctk.CTkFrame(status_card, fg_color="transparent")
        status_inner.pack(fill="x", padx=CARD_PADDING, pady=8)

        self._status_indicator = ctk.CTkLabel(
            status_inner, text="⬤ Server OFF",
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            text_color=STATUS_OFFLINE)
        self._status_indicator.pack(side="left", padx=(0, 24))

        self._stats_label = ctk.CTkLabel(
            status_inner,
            text="Pool: — | Active Leases: 0 | Available: — | Offers: 0 | ACKs: 0",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED)
        self._stats_label.pack(side="left", fill="x", expand=True)

        # ── Lease Table ──────────────────────────────────────────────────────
        lease_card = ctk.CTkFrame(self, fg_color=BG_CARD,
                                  corner_radius=CARD_CORNER_RADIUS)
        lease_card.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        lease_header = ctk.CTkFrame(lease_card, fg_color="transparent")
        lease_header.pack(fill="x", padx=CARD_PADDING, pady=(10, 4))

        ctk.CTkLabel(lease_header, text="Active Leases",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        # Column headers
        col_frame = ctk.CTkFrame(lease_card, fg_color=BG_DARK,
                                  corner_radius=4, height=30)
        col_frame.pack(fill="x", padx=CARD_PADDING, pady=(0, 2))
        col_frame.pack_propagate(False)

        cols = [("MAC Address", 180), ("IP Address", 150), ("Hostname", 180),
                ("Lease Remaining", 140), ("Status", 100)]
        for text, width in cols:
            ctk.CTkLabel(col_frame, text=text, width=width,
                         font=(FONT_FAMILY, FONT_SIZE_TINY, "bold"),
                         text_color=TEXT_MUTED, anchor="w").pack(
                             side="left", padx=(8, 0))

        # Scrollable lease list
        self._lease_scroll = ctk.CTkScrollableFrame(
            lease_card, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._lease_scroll.pack(fill="both", expand=True,
                                padx=CARD_PADDING, pady=(0, CARD_PADDING))
        enable_touch_scroll(self._lease_scroll)

    def _toggle_server(self):
        if self._server.is_running:
            self._server.stop()
            self._switch_label.configure(text="OFF", text_color=STATUS_ERROR)
            self._status_indicator.configure(text="⬤ Server OFF",
                                           text_color=STATUS_OFFLINE)
            self._stop_refresh()
        else:
            # Read config from UI
            config = DHCPServerConfig(
                pool_start=self._pool_start.get().strip(),
                pool_end=self._pool_end.get().strip(),
                subnet_mask=self._subnet_mask.get().strip() or "255.255.255.0",
                gateway=self._gateway.get().strip(),
                dns_primary=self._dns.get().strip(),
                lease_time=int(self._lease_time.get().strip() or "3600"),
            )
            self._server.configure(config)
            self._server.start()
            self._switch_label.configure(text="ON", text_color=STATUS_GOOD)
            self._start_refresh()

    def _on_lease_change(self, lease: DHCPLease):
        self.after(0, lambda: self._update_lease_row(lease))

    def _on_status_cb(self, status: DHCPServerStatus):
        self.after(0, lambda: self._update_server_status(status))

    def _on_error(self, error: str):
        self.after(0, lambda: self._show_error(error))

    def _update_server_status(self, status: DHCPServerStatus):
        if status.running:
            self._status_indicator.configure(text="⬤ Server ON",
                                           text_color=STATUS_GOOD)
        else:
            self._status_indicator.configure(text="⬤ Server OFF",
                                           text_color=STATUS_OFFLINE)
            if status.error:
                self._status_indicator.configure(
                    text=f"⬤ Error",
                    text_color=STATUS_ERROR)

        self._stats_label.configure(
            text=f"Pool: {status.total_pool_size} IPs  |  "
                 f"Active: {status.leases_active}  |  "
                 f"Available: {status.leases_available}  |  "
                 f"Offers: {status.offers_sent}  |  "
                 f"ACKs: {status.acks_sent}")

    def _update_lease_row(self, lease: DHCPLease):
        mac = lease.mac_address

        if mac in self._lease_rows:
            self._lease_rows[mac].destroy()

        row_color = BG_CARD_HOVER if len(self._lease_rows) % 2 == 0 else "transparent"
        row = ctk.CTkFrame(self._lease_scroll, fg_color=row_color,
                          corner_radius=2, height=32)
        row.pack(fill="x", pady=(0, 1))
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=mac, width=180,
                     font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         side="left", padx=(8, 0))

        ctk.CTkLabel(row, text=lease.ip_address, width=150,
                     font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                     text_color=SAS_BLUE, anchor="w").pack(
                         side="left", padx=(8, 0))

        ctk.CTkLabel(row, text=lease.hostname or "—", width=180,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_SECONDARY, anchor="w").pack(
                         side="left", padx=(8, 0))

        remaining_label = ctk.CTkLabel(row, text=lease.remaining_str, width=140,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED, anchor="w")
        remaining_label.pack(side="left", padx=(8, 0))
        remaining_label._lease_ref = lease  # For refresh updates

        status_color = STATUS_GOOD if lease.state == "active" else STATUS_WARN
        ctk.CTkLabel(row, text=lease.state.upper(), width=100,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                     text_color=status_color, anchor="w").pack(
                         side="left", padx=(8, 0))

        self._lease_rows[mac] = row

    def _start_refresh(self):
        """Start periodic refresh of lease timers."""
        self._refresh_lease_timers()

    def _stop_refresh(self):
        if self._refresh_timer:
            self.after_cancel(self._refresh_timer)
            self._refresh_timer = None

    def _refresh_lease_timers(self):
        """Update remaining time display for all leases."""
        for mac, row in list(self._lease_rows.items()):
            try:
                for child in row.winfo_children():
                    if hasattr(child, '_lease_ref'):
                        lease = child._lease_ref
                        child.configure(text=lease.remaining_str)
            except Exception:
                pass

        if self._server.is_running:
            self._refresh_timer = self.after(5000, self._refresh_lease_timers)

    def _show_error(self, error: str):
        self._status_indicator.configure(text=f"⬤ Error", text_color=STATUS_ERROR)
        # Reset switch if server failed to start
        if not self._server.is_running:
            self._switch.deselect()
            self._switch_label.configure(text="OFF", text_color=STATUS_ERROR)

    def on_show(self):
        pass
