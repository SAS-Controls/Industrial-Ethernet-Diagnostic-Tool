"""
SAS Network Diagnostic Tool — BOOTP Configuration View
Listen for BOOTP requests from unconfigured devices and assign IP addresses.
Replicates Rockwell's BOOTP/DHCP Server utility.
"""

import logging
import tkinter as tk
from datetime import datetime
from typing import Optional, Dict

import customtkinter as ctk

from core.bootp_server import BOOTPServer, BOOTPRequest, BOOTPAssignment, BOOTPServerStatus
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)


class BOOTPView(ctk.CTkFrame):
    """BOOTP Configuration Tool — assign IPs to unconfigured devices."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._server = BOOTPServer()
        self._server.on_request = self._on_request
        self._server.on_status = self._on_status_cb
        self._server.on_error = self._on_error
        self._request_widgets: Dict[str, ctk.CTkFrame] = {}
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=24, pady=(16, 8))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="📋  BOOTP Configuration Tool",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         side="left", fill="x", expand=True)

        self._status_label = ctk.CTkLabel(
            header, text="⬤ Stopped",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=STATUS_OFFLINE)
        self._status_label.pack(side="right")

        # ── Control Bar ───────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))

        ctrl_inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        ctrl_inner.pack(fill="x", padx=CARD_PADDING, pady=10)

        self._start_btn = ctk.CTkButton(
            ctrl_inner, text="Start Listening", width=140, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            command=self._toggle_server,
        )
        self._start_btn.pack(side="left", padx=(0, 16))

        # Stats
        self._stats_label = ctk.CTkLabel(
            ctrl_inner, text="Requests: 0  |  Unique MACs: 0  |  Assigned: 0",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED)
        self._stats_label.pack(side="left")

        # Info
        ctk.CTkLabel(
            ctrl_inner, text="Requires Run as Administrator",
            font=(FONT_FAMILY, FONT_SIZE_TINY),
            text_color=STATUS_WARN).pack(side="right")

        # ── Description ──────────────────────────────────────────────────────
        desc = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        desc.pack(fill="x", padx=24, pady=(0, 4))
        ctk.CTkLabel(
            desc,
            text=("This tool listens for BOOTP requests from unconfigured devices "
                  "(like Allen-Bradley modules in BOOTP mode). When a device is "
                  "detected, enter the IP address you want to assign and click "
                  "'Assign'. The device will receive the IP configuration."),
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_SECONDARY, wraplength=800, justify="left",
            anchor="w",
        ).pack(fill="x", padx=CARD_PADDING, pady=10)

        # ── Device List ──────────────────────────────────────────────────────
        self._devices_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._devices_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        enable_touch_scroll(self._devices_scroll)

        # Placeholder
        self._placeholder = ctk.CTkLabel(
            self._devices_scroll,
            text="Click 'Start Listening' to begin detecting BOOTP requests.\n\n"
                 "Connect directly to the device or to the same switch.\n"
                 "Unconfigured devices will appear here automatically.",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_MUTED, justify="center",
        )
        self._placeholder.pack(expand=True, pady=60)

    def _toggle_server(self):
        if self._server.is_running:
            self._server.stop()
            self._start_btn.configure(text="Start Listening",
                                     fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK)
            self._status_label.configure(text="⬤ Stopped", text_color=STATUS_OFFLINE)
        else:
            self._server.start()
            self._start_btn.configure(text="Stop Listening",
                                     fg_color=STATUS_ERROR, hover_color="#DC2626")

    def _on_request(self, req: BOOTPRequest):
        self.after(0, lambda: self._add_device_card(req))

    def _on_status_cb(self, status: BOOTPServerStatus):
        self.after(0, lambda: self._update_status(status))

    def _on_error(self, error: str):
        self.after(0, lambda: self._show_error(error))

    def _update_status(self, status: BOOTPServerStatus):
        if status.running:
            self._status_label.configure(text="⬤ Listening", text_color=STATUS_GOOD)
        else:
            self._status_label.configure(text="⬤ Stopped", text_color=STATUS_OFFLINE)
            if status.error:
                self._status_label.configure(
                    text=f"⬤ Error: {status.error[:40]}",
                    text_color=STATUS_ERROR)

        self._stats_label.configure(
            text=f"Requests: {status.requests_seen}  |  "
                 f"Unique MACs: {status.unique_macs}  |  "
                 f"Assigned: {status.assignments_sent}")

    def _add_device_card(self, req: BOOTPRequest):
        mac = req.mac_address
        if self._placeholder.winfo_exists():
            self._placeholder.destroy()

        # Update existing card or create new
        if mac in self._request_widgets:
            # Update timestamp on existing card
            card = self._request_widgets[mac]
            for child in card.winfo_children():
                if hasattr(child, '_is_time_label'):
                    child.configure(text=f"Last seen: {req.timestamp.strftime('%H:%M:%S')}")
            return

        # New device card
        card = ctk.CTkFrame(self._devices_scroll, fg_color=BG_CARD,
                           corner_radius=CARD_CORNER_RADIUS)
        card.pack(fill="x", pady=(0, 8))

        # Row 1: MAC + vendor info
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))

        ctk.CTkLabel(row1, text="📡", font=(FONT_FAMILY, FONT_SIZE_HEADING)).pack(
            side="left", padx=(0, 8))

        info_frame = ctk.CTkFrame(row1, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(info_frame, text=f"MAC: {mac}",
                     font=(FONT_FAMILY_MONO, FONT_SIZE_BODY, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(fill="x")

        vendor_text = req.vendor_class or "Unknown Device"
        if req.hostname:
            vendor_text += f"  •  Host: {req.hostname}"
        ctk.CTkLabel(info_frame, text=vendor_text,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_SECONDARY, anchor="w").pack(fill="x")

        time_label = ctk.CTkLabel(info_frame,
                     text=f"Last seen: {req.timestamp.strftime('%H:%M:%S')}",
                     font=(FONT_FAMILY, FONT_SIZE_TINY),
                     text_color=TEXT_MUTED, anchor="w")
        time_label.pack(fill="x")
        time_label._is_time_label = True

        # Row 2: Assignment fields
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=CARD_PADDING, pady=(4, CARD_PADDING))

        ctk.CTkLabel(row2, text="IP:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        ip_entry = ctk.CTkEntry(
            row2, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="192.168.1.100",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        ip_entry.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row2, text="Mask:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        mask_entry = ctk.CTkEntry(
            row2, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        mask_entry.pack(side="left", padx=(0, 8))
        mask_entry.insert(0, "255.255.255.0")

        ctk.CTkLabel(row2, text="Gateway:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        gw_entry = ctk.CTkEntry(
            row2, width=150, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="(optional)",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        gw_entry.pack(side="left", padx=(0, 12))

        # Status label for this card
        card_status = ctk.CTkLabel(
            row2, text="",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=STATUS_GOOD)
        card_status.pack(side="right", padx=(8, 0))

        # Assign button
        def _assign():
            ip = ip_entry.get().strip()
            mask = mask_entry.get().strip() or "255.255.255.0"
            gw = gw_entry.get().strip()
            if not ip:
                card_status.configure(text="Enter an IP address", text_color=STATUS_ERROR)
                return
            self._server.set_assignment(mac, ip, mask, gw)
            card_status.configure(text=f"Assigned {ip} — waiting for next request...",
                                text_color=STATUS_GOOD)

        ctk.CTkButton(
            row2, text="Assign", width=80, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_ORANGE, hover_color=SAS_ORANGE_DARK,
            command=_assign,
        ).pack(side="right")

        self._request_widgets[mac] = card

    def _show_error(self, error: str):
        self._status_label.configure(text=f"⬤ Error", text_color=STATUS_ERROR)

    def on_show(self):
        pass
