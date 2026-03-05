"""
SAS Network Diagnostic Tool — Multi-Device Monitor View
Monitor multiple Ethernet devices simultaneously with a real-time trend chart
and analytics table.  Chart is pure tkinter Canvas — no external dependencies.

New in this revision:
  - Event markers: timestamped vertical lines on chart (Mark Event button)
  - Jitter bands: shaded min/max envelope around each device's trend line
  - Rolling average line overlay per device
  - Device Status Event Log panel (shows online/offline transitions)
  - Jitter (std dev) column in analytics table
"""

import ipaddress
import logging
import math
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from core.multi_monitor import (
    MultiDeviceMonitor, DeviceTarget, DeviceAnalytics,
    MultiPollSample, DeviceStatusEvent, CHART_COLORS,
)
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)

# ── Chart layout constants ───────────────────────────────────────────────────
CHART_HEIGHT       = 280
CHART_LEFT_MARGIN  = 52
CHART_RIGHT_MARGIN = 16
CHART_TOP_MARGIN   = 10
CHART_BOTTOM_MARGIN = 24
CHART_VISIBLE      = 200

ROLLING_AVG_WINDOW = 10


def resolve_color(c):
    if isinstance(c, (list, tuple)):
        return c[1]
    return c


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blend_color(hex_color: str, alpha: float = 0.25, bg: str = "#0D1117") -> str:
    fr, fg_, fb = _hex_to_rgb(hex_color)
    br, bg_r, bb = _hex_to_rgb(bg)
    r = int(fr * alpha + br * (1 - alpha))
    g = int(fg_ * alpha + bg_r * (1 - alpha))
    b = int(fb * alpha + bb * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


def _rolling_avg(data: List[Optional[float]], window: int) -> List[Optional[float]]:
    result = []
    for i in range(len(data)):
        start = max(0, i - window + 1)
        chunk = [v for v in data[start:i + 1] if v is not None]
        result.append(sum(chunk) / len(chunk) if chunk else None)
    return result


def _rolling_band(data: List[Optional[float]], window: int):
    mins, maxs = [], []
    for i in range(len(data)):
        start = max(0, i - window + 1)
        chunk = [v for v in data[start:i + 1] if v is not None]
        if chunk:
            mins.append(min(chunk))
            maxs.append(max(chunk))
        else:
            mins.append(None)
            maxs.append(None)
    return mins, maxs


class EventMarker:
    def __init__(self, sample_index: int, timestamp: datetime, label: str):
        self.sample_index = sample_index
        self.timestamp = timestamp
        self.label = label


class MultiMonitorView(ctk.CTkFrame):
    """Monitor multiple devices with live trend chart and analytics."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._monitor = MultiDeviceMonitor()
        self._targets: List[DeviceTarget] = []
        self._running = False
        self._chart_timer = None
        self._chart_last_w = 800

        self._trend_values: Dict[str, List[Optional[float]]] = {}
        self._trend_timestamps: List[datetime] = []
        self._event_markers: List[EventMarker] = []

        self._show_avg   = tk.BooleanVar(value=True)
        self._show_band  = tk.BooleanVar(value=True)
        self._stacked    = tk.BooleanVar(value=False)

        # Solo mode — when set, only this IP is rendered on the chart
        self._solo_ip: Optional[str] = None

        # Per-device line style prefs: ip -> {"width": float, "dash": tuple}
        self._line_prefs: Dict[str, dict] = {}
        # Stacked-mode canvas store: list of (ip, tk.Canvas)
        self._stacked_canvases: List[Tuple[str, tk.Canvas]] = []

        # Last analysis reports: Dict[ip, AnalysisReport]
        self._analysis_reports: dict = {}

        self._build_ui()

    def on_show(self):
        pass

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 0))

        ctk.CTkLabel(header, text="📊  Multi-Device Monitor",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")

        self._export_btn = ctk.CTkButton(
            btn_frame, text="📄 Export Report",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=SAS_BLUE, text_color=SAS_BLUE_LIGHT,
            hover_color=BG_CARD_HOVER, width=130, height=BUTTON_HEIGHT,
            command=self._export_report, state="disabled",
        )
        self._export_btn.pack(side="left", padx=(0, 8))

        self._analyze_btn = ctk.CTkButton(
            btn_frame, text="🔍 Analyze",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=BG_CARD_HOVER, width=110, height=BUTTON_HEIGHT,
            command=self._run_analysis, state="disabled",
        )
        self._analyze_btn.pack(side="left", padx=(0, 8))

        self._csv_btn = ctk.CTkButton(
            btn_frame, text="📋 Export CSV",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=BG_CARD_HOVER, width=120, height=BUTTON_HEIGHT,
            command=self._export_csv, state="disabled",
        )
        self._csv_btn.pack(side="left")

        # Config card
        config_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
                                    border_width=1, border_color=BORDER_COLOR)
        config_card.pack(fill="x", padx=20, pady=(12, 0))

        config_inner = ctk.CTkFrame(config_card, fg_color="transparent")
        config_inner.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)

        top_row = ctk.CTkFrame(config_inner, fg_color="transparent")
        top_row.pack(fill="x")

        ctk.CTkLabel(top_row, text="Device IPs:",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._ip_entry = ctk.CTkEntry(
            top_row,
            placeholder_text="e.g. 192.168.1.10-192.168.1.20  or  10.0.0.1, 10.0.0.5",
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
            width=400, height=BUTTON_HEIGHT,
        )
        self._ip_entry.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(top_row, text="Rate:",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))

        self._rate_var = ctk.StringVar(value="1 sec")
        ctk.CTkOptionMenu(
            top_row, variable=self._rate_var,
            values=["500 ms", "1 sec", "2 sec", "5 sec", "10 sec", "30 sec"],
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color=BG_INPUT, button_color=SAS_BLUE,
            button_hover_color=SAS_BLUE_DARK, dropdown_fg_color=BG_MEDIUM,
            width=90, height=BUTTON_HEIGHT,
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(top_row, text="Timeout:",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 4))

        self._timeout_entry = ctk.CTkEntry(
            top_row, font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
            width=60, height=BUTTON_HEIGHT,
        )
        self._timeout_entry.insert(0, "2000")
        self._timeout_entry.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(top_row, text="ms", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(side="left", padx=(0, 12))

        self._start_btn = ctk.CTkButton(
            top_row, text="▶ Start Monitor",
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            text_color="white", width=140, height=BUTTON_HEIGHT,
            command=self._toggle_monitor,
        )
        self._start_btn.pack(side="left", padx=(0, 4))

        self._status_label = ctk.CTkLabel(
            config_inner, text="Enter device IPs (ranges supported) and click Start Monitor",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._status_label.pack(fill="x", pady=(6, 0))

        # Scrollable content
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._scroll.pack(fill="both", expand=True, padx=20, pady=(8, 20))
        enable_touch_scroll(self._scroll)

        self._build_chart_card(self._scroll)
        self._build_status_log(self._scroll)
        self._build_table_card(self._scroll)
        self._build_analysis_section(self._scroll)

    # ── Chart Card ───────────────────────────────────────────────────────────

    def _build_chart_card(self, parent):
        chart_card = ctk.CTkFrame(
            parent, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        chart_card.pack(fill="x", pady=(0, 10))

        chart_hdr = ctk.CTkFrame(chart_card, fg_color="transparent")
        chart_hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))

        ctk.CTkLabel(chart_hdr, text="Response Time Trend",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        self._chart_points_label = ctk.CTkLabel(
            chart_hdr, text="", font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED)
        self._chart_points_label.pack(side="left", padx=(12, 0))

        # Solo mode indicator (hidden until a device is soloed)
        self._solo_label = ctk.CTkLabel(
            chart_hdr, text="",
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
            text_color=SAS_ORANGE)
        self._solo_label.pack(side="left", padx=(10, 0))

        # Right side controls
        ctrl = ctk.CTkFrame(chart_hdr, fg_color="transparent")
        ctrl.pack(side="right")

        self._show_all_btn = ctk.CTkButton(
            ctrl, text="👁 Show All",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            fg_color=BG_MEDIUM, hover_color=BG_CARD_HOVER,
            text_color=TEXT_SECONDARY, width=85, height=26,
            command=self._show_all_devices,
        )
        # Packed on demand when solo mode is active
        self._show_all_btn.pack(side="left", padx=(0, 8))
        self._show_all_btn.pack_forget()

        ctk.CTkCheckBox(ctrl, text="Avg Line", variable=self._show_avg,
                        font=(FONT_FAMILY, FONT_SIZE_SMALL),
                        text_color=TEXT_MUTED, fg_color=SAS_BLUE,
                        hover_color=SAS_BLUE_DARK, height=20,
                        checkbox_width=16, checkbox_height=16,
                        command=self._draw_chart).pack(side="left", padx=(0, 10))

        ctk.CTkCheckBox(ctrl, text="Min/Max Band", variable=self._show_band,
                        font=(FONT_FAMILY, FONT_SIZE_SMALL),
                        text_color=TEXT_MUTED, fg_color=SAS_BLUE,
                        hover_color=SAS_BLUE_DARK, height=20,
                        checkbox_width=16, checkbox_height=16,
                        command=self._draw_chart).pack(side="left", padx=(0, 10))

        ctk.CTkCheckBox(ctrl, text="⊞ Stack", variable=self._stacked,
                        font=(FONT_FAMILY, FONT_SIZE_SMALL),
                        text_color=TEXT_MUTED, fg_color=SAS_BLUE,
                        hover_color=SAS_BLUE_DARK, height=20,
                        checkbox_width=16, checkbox_height=16,
                        command=self._on_stack_toggle).pack(side="left", padx=(0, 12))

        self._mark_btn = ctk.CTkButton(
            ctrl, text="📍 Mark Event",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            fg_color=SAS_ORANGE, hover_color=SAS_ORANGE_DARK,
            text_color="white", width=105, height=26,
            command=self._mark_event, state="disabled",
        )
        self._mark_btn.pack(side="left")

        # Combined-mode canvas (default view)
        self._chart_canvas = tk.Canvas(
            chart_card, height=CHART_HEIGHT,
            bg=resolve_color(BG_DARK),
            highlightthickness=0, bd=0,
        )
        self._chart_canvas.pack(fill="x", padx=8, pady=(4, 4))
        self._chart_canvas.bind("<Configure>", self._on_chart_resize)
        self._chart_canvas.bind("<Button-3>", self._on_chart_right_click)
        self._chart_canvas.bind("<Button-2>", self._on_chart_right_click)

        # Stacked-mode container (hidden until stack toggled on)
        self._stacked_frame = tk.Frame(chart_card, bg=resolve_color(BG_DARK))

        self._legend_frame = ctk.CTkFrame(chart_card, fg_color="transparent")
        self._legend_frame.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

        self._draw_empty_chart()

    # ── Status Event Log ─────────────────────────────────────────────────────

    def _build_status_log(self, parent):
        log_card = ctk.CTkFrame(
            parent, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        log_card.pack(fill="x", pady=(0, 10))

        log_hdr = ctk.CTkFrame(log_card, fg_color="transparent")
        log_hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))

        ctk.CTkLabel(log_hdr, text="🔔  Device Status & Event Log",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        ctk.CTkLabel(log_hdr,
                     text="Device online/offline transitions · User event markers",
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(side="left", padx=(14, 0))

        self._status_log_text = ctk.CTkTextbox(
            log_card, height=110,
            fg_color=resolve_color(BG_DARK),
            text_color=TEXT_SECONDARY,
            font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
            activate_scrollbars=True, wrap="none",
        )
        self._status_log_text.pack(fill="x", padx=8, pady=(0, 10))
        self._status_log_text.configure(state="disabled")
        self._status_log_text.tag_config("online",  foreground="#22C55E")
        self._status_log_text.tag_config("offline", foreground="#EF4444")
        self._status_log_text.tag_config("marker",  foreground="#F59E0B")
        self._status_log_text.tag_config("info",    foreground=resolve_color(TEXT_MUTED))

    def _log_status(self, message: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._status_log_text.configure(state="normal")
        self._status_log_text.insert("end", f"[{ts}]  {message}\n", tag)
        self._status_log_text.see("end")
        self._status_log_text.configure(state="disabled")

    def _on_device_status_change(self, evt: DeviceStatusEvent):
        if evt.came_online:
            msg = f"✅  {evt.label} came back ONLINE  ({evt.ping_ms:.1f}ms)" if evt.ping_ms else f"✅  {evt.label} came back ONLINE"
            tag = "online"
        else:
            msg = f"❌  {evt.label} went OFFLINE"
            tag = "offline"
        self.after(0, lambda: self._log_status(msg, tag))

    # ── Analytics Table Card ─────────────────────────────────────────────────

    def _build_table_card(self, parent):
        table_card = ctk.CTkFrame(
            parent, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        table_card.pack(fill="x", pady=(0, 10))

        table_hdr = ctk.CTkFrame(table_card, fg_color="transparent")
        table_hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))
        ctk.CTkLabel(table_hdr, text="Device Analytics",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        ctk.CTkLabel(table_hdr,
                     text="Jitter (σ) = standard deviation of ping times.  "
                          "High jitter indicates an unstable connection even if avg ping looks acceptable.",
                     font=(FONT_FAMILY, FONT_SIZE_TINY),
                     text_color=TEXT_MUTED).pack(side="left", padx=(12, 0))

        self._build_analytics_table(table_card)

    def _build_analytics_table(self, parent):
        tree_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tree_frame.pack(fill="x", padx=8, pady=(0, 8))

        columns = ("ip", "status", "uptime", "ping_avg", "ping_min", "ping_max",
                    "jitter", "ping_loss", "cip_avg", "outages", "longest", "product")
        col_names = {
            "ip": "IP Address", "status": "Status", "uptime": "Uptime %",
            "ping_avg": "Ping Avg", "ping_min": "Ping Min", "ping_max": "Ping Max",
            "jitter": "Jitter (σ)", "ping_loss": "Ping Loss %", "cip_avg": "CIP Avg",
            "outages": "Outages", "longest": "Longest Out", "product": "Product",
        }
        col_widths = {
            "ip": 130, "status": 70, "uptime": 72, "ping_avg": 72,
            "ping_min": 68, "ping_max": 68, "jitter": 70, "ping_loss": 78,
            "cip_avg": 68, "outages": 62, "longest": 82, "product": 145,
        }

        bg_c  = resolve_color(BG_DARK)
        fg_c  = resolve_color(TEXT_PRIMARY)
        hdr_c = resolve_color(BG_MEDIUM)
        sel_c = resolve_color(SAS_BLUE)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Multi.Treeview",
                         background=bg_c, foreground=fg_c, fieldbackground=bg_c,
                         font=(FONT_FAMILY, 10), rowheight=28, borderwidth=0)
        style.configure("Multi.Treeview.Heading",
                         background=hdr_c, foreground=fg_c,
                         font=(FONT_FAMILY, 10, "bold"), borderwidth=1, relief="flat")
        style.map("Multi.Treeview.Heading", background=[("active", hdr_c)])
        style.map("Multi.Treeview",
                   background=[("selected", sel_c)],
                   foreground=[("selected", "#FFFFFF")])

        self._analytics_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            style="Multi.Treeview", height=8,
        )

        for col in columns:
            self._analytics_tree.heading(col, text=col_names[col])
            self._analytics_tree.column(col, width=col_widths.get(col, 75),
                                         minwidth=50, anchor="center")
        self._analytics_tree.column("ip",      anchor="w")
        self._analytics_tree.column("product", anchor="w")

        scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                                command=self._analytics_tree.yview)
        self._analytics_tree.configure(yscrollcommand=scroll.set)
        self._analytics_tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")

        self._analytics_tree.tag_configure("online",  foreground="#22C55E")
        self._analytics_tree.tag_configure("offline", foreground="#EF4444")
        self._analytics_tree.tag_configure("unknown", foreground=resolve_color(TEXT_MUTED))
        self._analytics_tree.tag_configure("warn",    foreground="#F59E0B")

    # ── Event Markers ────────────────────────────────────────────────────────

    def _mark_event(self):
        label = simpledialog.askstring(
            "Mark Event",
            "Enter a label for this event marker\n(e.g. 'Connected Device 5', 'Unplugged switch port 3'):",
            initialvalue="Device connected",
            parent=self,
        )
        if label is None:
            return

        sample_index = max(0, len(self._trend_timestamps) - 1)
        ts = self._trend_timestamps[sample_index] if self._trend_timestamps else datetime.now()
        self._event_markers.append(EventMarker(sample_index, ts, label))

        self._log_status(
            f"📍  Event marker placed: '{label}'  @  {ts.strftime('%H:%M:%S')}  "
            f"(sample #{sample_index})",
            "marker",
        )
        self._draw_chart()

    # ── Canvas Chart ─────────────────────────────────────────────────────────

    def _on_chart_resize(self, event):
        if event.width > 50:
            self._chart_last_w = event.width
            self._draw_chart()

    def _draw_empty_chart(self):
        c = self._chart_canvas
        c.delete("all")
        w = self._chart_last_w
        h = CHART_HEIGHT
        px0, px1 = CHART_LEFT_MARGIN, w - CHART_RIGHT_MARGIN
        py0, py1 = CHART_TOP_MARGIN, h - CHART_BOTTOM_MARGIN

        for frac in [0.25, 0.5, 0.75]:
            y = py0 + int((py1 - py0) * frac)
            c.create_line(px0, y, px1, y, fill=resolve_color(BORDER_COLOR), dash=(2, 4))

        c.create_text(w // 2, h // 2,
                       text="Start monitoring to see response times",
                       fill=resolve_color(TEXT_MUTED), font=(FONT_FAMILY, 11))

    # ── Stacked Chart Mode ───────────────────────────────────────────────────

    def _on_stack_toggle(self):
        """Switch between combined (single chart) and stacked (per-device) mode."""
        if self._stacked.get():
            self._chart_canvas.pack_forget()
            self._rebuild_stacked_canvases()
            self._stacked_frame.pack(fill="x", padx=8, pady=(4, 4))
        else:
            self._stacked_frame.pack_forget()
            self._chart_canvas.pack(fill="x", padx=8, pady=(4, 4))
        self._draw_chart()

    def _rebuild_stacked_canvases(self):
        """Destroy and recreate per-device canvases in the stacked container."""
        for w in self._stacked_frame.winfo_children():
            w.destroy()
        self._stacked_canvases.clear()
        if not self._targets:
            return
        n = len(self._targets)
        h = 120 if n > 2 else (160 if n == 2 else 280)
        for t in self._targets:
            row = tk.Frame(self._stacked_frame, bg=resolve_color(BG_DARK))
            row.pack(fill="x", pady=(0, 2))
            c = tk.Canvas(row, height=h, bg=resolve_color(BG_DARK),
                          highlightthickness=0, bd=0)
            c.pack(fill="x")
            self._stacked_canvases.append((t.ip, c, h))

    def _stacked_height(self) -> int:
        n = max(1, len(self._targets))
        if n <= 1: return 280
        if n == 2: return 160
        return 120

    def _draw_stacked_chart(self):
        """Render one mini-chart per device, stacked vertically with shared X axis."""
        if not self._stacked_canvases:
            self._rebuild_stacked_canvases()
        if not self._stacked_canvases:
            return

        total_pts = len(self._trend_timestamps)
        end   = total_pts
        start = max(0, end - CHART_VISIBLE)
        n_pts = end - start
        timestamps = self._trend_timestamps[start:end]

        # Determine chart width from first canvas
        first_canvas = self._stacked_canvases[0][1]
        w = first_canvas.winfo_width()
        if w < 100:
            w = self._chart_last_w

        px0 = CHART_LEFT_MARGIN
        px1 = w - CHART_RIGHT_MARGIN
        pw  = px1 - px0
        if pw < 20:
            return

        x_step = pw / max(n_pts - 1, 1) if n_pts > 1 else pw
        n_devs = len(self._stacked_canvases)
        grid_c = resolve_color(BORDER_COLOR)
        text_c = resolve_color(TEXT_MUTED)

        for dev_idx, (ip, c, h) in enumerate(self._stacked_canvases):
            c.delete("all")
            is_last = (dev_idx == n_devs - 1)
            py0 = CHART_TOP_MARGIN + 14   # extra room for device label
            py1 = h - (CHART_BOTTOM_MARGIN if is_last else 6)
            ph  = max(py1 - py0, 20)

            target = next((t for t in self._targets if t.ip == ip), None)
            if not target:
                continue

            data = self._trend_values.get(ip, [])[start:end]

            # ── Device name label (top-left of each mini-chart) ──
            c.create_text(px0, 5, text=target.display_name,
                           fill=target.color, anchor="w",
                           font=("Consolas", 9, "bold"))

            # ── Y-axis scale for this device ──
            vals = [v for v in data if v is not None]
            max_val = max(vals) * 1.20 if vals else 10.0
            max_val = max(max_val, 1.0)
            for n_tick in [2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]:
                if max_val <= n_tick:
                    max_val = float(n_tick)
                    break
            else:
                max_val = float(math.ceil(max_val / 500) * 500)

            def val_to_y(v, _py0=py0, _ph=ph, _mx=max_val):
                return max(_py0, min(_py0 + _ph, _py0 + _ph * (1.0 - v / _mx)))

            # ── Grid lines ──
            for frac in [0.0, 0.5, 1.0]:
                y = py0 + int(ph * frac)
                c.create_line(px0, y, px1, y, fill=grid_c, dash=(2, 4))
                val = max_val * (1.0 - frac)
                lbl = f"{val:.0f}" if val >= 10 else f"{val:.1f}"
                c.create_text(px0 - 4, y, text=lbl, fill=text_c, anchor="e",
                               font=("Consolas", 8))

            c.create_text(px0 - 4, py0 - 8, text="ms", fill=text_c, anchor="e",
                           font=("Consolas", 7))

            # ── Time labels on bottom device only ──
            if is_last and n_pts >= 2:
                label_step = max(1, n_pts // 6)
                for idx in range(0, n_pts, label_step):
                    x = px0 + idx * x_step
                    if idx < len(timestamps):
                        c.create_text(x, py1 + 10, text=timestamps[idx].strftime("%H:%M:%S"),
                                       fill=text_c, anchor="n", font=("Consolas", 7))

            if not data:
                continue

            # ── Jitter band ──
            if self._show_band.get():
                band_color = _blend_color(target.color, 0.22)
                band_mins, band_maxs = _rolling_band(data, ROLLING_AVG_WINDOW)
                poly = []
                for i, (mn, mx) in enumerate(zip(band_mins, band_maxs)):
                    if mn is not None and mx is not None:
                        poly.append((px0 + i * x_step, val_to_y(mx)))
                for i in range(len(band_maxs) - 1, -1, -1):
                    if band_mins[i] is not None and band_maxs[i] is not None:
                        poly.append((px0 + i * x_step, val_to_y(band_mins[i])))
                if len(poly) >= 4:
                    flat = [coord for p in poly for coord in p]
                    c.create_polygon(*flat, fill=band_color, outline="", stipple="gray25")

            # ── Raw line ──
            prefs = self._line_prefs.get(ip, self._default_line_pref())
            base_w = prefs["width"]
            base_d = prefs["dash"]
            pts = []
            for i, val in enumerate(data):
                x = px0 + i * x_step
                if val is not None:
                    pts.append((x, val_to_y(val)))
                else:
                    c.create_rectangle(x - 2, py1 - 5, x + 2, py1 - 1,
                                        fill="#EF4444", outline="")
                    if len(pts) >= 2:
                        kw = dict(fill=target.color, width=base_w, smooth=True)
                        if base_d: kw["dash"] = base_d
                        c.create_line(*[coord for p in pts for coord in p], **kw)
                    pts = []
            if len(pts) >= 2:
                kw = dict(fill=target.color, width=base_w, smooth=True)
                if base_d: kw["dash"] = base_d
                c.create_line(*[coord for p in pts for coord in p], **kw)

            # ── Live value dot + label (right edge) ──
            last_val = next((v for v in reversed(data) if v is not None), None)
            if last_val is not None:
                lx = px0 + (len(data) - 1) * x_step
                ly = val_to_y(last_val)
                c.create_oval(lx - 3, ly - 3, lx + 3, ly + 3,
                               fill=target.color, outline="white", width=1)
                c.create_text(lx + 6, ly, text=f"{last_val:.1f}ms",
                               fill=target.color, anchor="w",
                               font=("Consolas", 8, "bold"))

            # ── Event markers ──
            for marker in self._event_markers:
                m_idx = marker.sample_index - start
                if 0 <= m_idx < n_pts:
                    x = px0 + m_idx * x_step
                    c.create_line(x, py0, x, py1, fill="#F59E0B", width=1, dash=(3, 3))

    def _draw_chart(self):
        if self._stacked.get():
            self._draw_stacked_chart()
            return

        c = self._chart_canvas
        c.delete("all")
        w = self._chart_last_w
        h = CHART_HEIGHT

        if w < 100:
            return

        total_pts = len(self._trend_timestamps)
        if total_pts < 2:
            self._draw_empty_chart()
            return

        end   = total_pts
        start = max(0, end - CHART_VISIBLE)
        n_pts = end - start

        px0 = CHART_LEFT_MARGIN
        px1 = w - CHART_RIGHT_MARGIN
        py0 = CHART_TOP_MARGIN
        py1 = h - CHART_BOTTOM_MARGIN
        pw  = px1 - px0
        ph  = py1 - py0

        if pw < 20 or ph < 20:
            return

        # Y-axis scale
        all_vals = []
        for t in self._targets:
            for v in self._trend_values.get(t.ip, [])[start:end]:
                if v is not None:
                    all_vals.append(v)

        max_val = max(all_vals) * 1.20 if all_vals else 10.0
        max_val = max(max_val, 1.0)
        for n in [2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]:
            if max_val <= n:
                max_val = n
                break
        else:
            max_val = math.ceil(max_val / 500) * 500

        grid_c = resolve_color(BORDER_COLOR)
        text_c = resolve_color(TEXT_MUTED)

        # Grid + Y labels
        for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = py0 + int(ph * frac)
            c.create_line(px0, y, px1, y, fill=grid_c, dash=(2, 4))
            val = max_val * (1.0 - frac)
            lbl = f"{val:.0f}" if val >= 10 else (f"{val:.1f}" if val >= 1 else f"{val:.2f}")
            c.create_text(px0 - 4, y, text=lbl, fill=text_c, anchor="e",
                           font=("Consolas", 8))
        c.create_text(px0 - 4, py0 - 8, text="ms", fill=text_c, anchor="e",
                       font=("Consolas", 8))

        # X-axis time labels
        x_step = pw / max(n_pts - 1, 1)
        timestamps = self._trend_timestamps[start:end]
        label_step = max(1, n_pts // min(6, n_pts))
        for idx in range(0, n_pts, label_step):
            x = px0 + idx * x_step
            if idx < len(timestamps):
                c.create_text(x, py1 + 10, text=timestamps[idx].strftime("%H:%M:%S"),
                               fill=text_c, anchor="n", font=("Consolas", 7))

        def val_to_y(v: float) -> float:
            return max(py0, min(py1, py0 + ph * (1.0 - v / max_val)))

        # ── Determine which devices to draw ──
        if self._solo_ip:
            draw_targets = [t for t in self._targets if t.ip == self._solo_ip]
        else:
            draw_targets = self._targets

        # ── Draw each device ──
        for t in draw_targets:
            is_solo = self._solo_ip is not None
            prefs = self._line_prefs.get(t.ip, self._default_line_pref())
            base_w = prefs["width"]
            base_d = prefs["dash"]
            # Solo mode boosts line weight by 0.5px for readability
            line_width_raw = base_w + (0.5 if is_solo else 0)
            line_width_avg = min(base_w + 1.0, 4.0)

            data = self._trend_values.get(t.ip, [])[start:end]
            if not data:
                continue

            band_color = _blend_color(t.color, 0.22)
            avg_data = _rolling_avg(data, ROLLING_AVG_WINDOW)
            band_mins, band_maxs = _rolling_band(data, ROLLING_AVG_WINDOW)

            # Jitter band polygon (stippled fill)
            if self._show_band.get():
                poly = []
                for i, (mn, mx) in enumerate(zip(band_mins, band_maxs)):
                    if mn is not None and mx is not None:
                        poly.append((px0 + i * x_step, val_to_y(mx)))
                for i in range(len(band_maxs) - 1, -1, -1):
                    if band_mins[i] is not None and band_maxs[i] is not None:
                        poly.append((px0 + i * x_step, val_to_y(band_mins[i])))
                if len(poly) >= 4:
                    flat = [coord for p in poly for coord in p]
                    c.create_polygon(*flat, fill=band_color, outline="", stipple="gray25")

            # Avg line — always dashed regardless of device style
            avg_dash = (7, 3) if not base_d else base_d
            if self._show_avg.get():
                avg_pts = []
                for i, avg in enumerate(avg_data):
                    if avg is not None:
                        avg_pts.append((px0 + i * x_step, val_to_y(avg)))
                    else:
                        if len(avg_pts) >= 2:
                            c.create_line(*[coord for p in avg_pts for coord in p],
                                           fill=t.color, width=line_width_avg,
                                           smooth=True, dash=avg_dash)
                        avg_pts = []
                if len(avg_pts) >= 2:
                    c.create_line(*[coord for p in avg_pts for coord in p],
                                   fill=t.color, width=line_width_avg,
                                   smooth=True, dash=avg_dash)

            # Raw data line — uses device's chosen dash style
            pts = []
            for i, val in enumerate(data):
                x = px0 + i * x_step
                if val is not None:
                    pts.append((x, val_to_y(val)))
                else:
                    c.create_rectangle(x - 2, py1 - 5, x + 2, py1 - 1,
                                        fill="#EF4444", outline="")
                    if len(pts) >= 2:
                        kw = dict(fill=t.color, width=line_width_raw, smooth=True)
                        if base_d: kw["dash"] = base_d
                        c.create_line(*[coord for p in pts for coord in p], **kw)
                    pts = []
            if len(pts) >= 2:
                kw = dict(fill=t.color, width=line_width_raw, smooth=True)
                if base_d: kw["dash"] = base_d
                c.create_line(*[coord for p in pts for coord in p], **kw)

            # In solo mode, draw a current-value label at the right end of the line
            if is_solo:
                last_val = next((v for v in reversed(data) if v is not None), None)
                if last_val is not None:
                    lx = px0 + (len(data) - 1) * x_step
                    ly = val_to_y(last_val)
                    c.create_oval(lx - 4, ly - 4, lx + 4, ly + 4,
                                   fill=t.color, outline="white", width=1)
                    c.create_text(lx + 8, ly, text=f"{last_val:.1f}ms",
                                   fill=t.color, anchor="w",
                                   font=("Consolas", 9, "bold"))

        # ── Event marker vertical lines ──
        for marker in self._event_markers:
            m_idx = marker.sample_index - start
            if 0 <= m_idx < n_pts:
                x = px0 + m_idx * x_step
                c.create_line(x, py0, x, py1, fill="#F59E0B", width=1.5, dash=(4, 3))
                c.create_rectangle(x - 2, py0, x + 2, py0 + 12,
                                    fill="#F59E0B", outline="")
                lbl = marker.label[:16] + "…" if len(marker.label) > 16 else marker.label
                c.create_text(x + 4, py0 + 2, text=lbl, fill="#F59E0B",
                               anchor="nw", font=("Consolas", 7))

    # ── Legend ────────────────────────────────────────────────────────────────

    # Dash patterns keyed by display name
    DASH_STYLES = {
        "Solid":  (),
        "Dashed": (8, 4),
        "Dotted": (2, 4),
    }
    # Thickness options
    WIDTH_OPTIONS = {"1px": 1.0, "2px": 2.0, "3px": 3.0, "4px": 4.0}

    def _default_line_pref(self) -> dict:
        return {"width": 1.5, "dash": ()}

    def _build_legend(self):
        """Build device legend: color swatch (click=color picker), device name (click=solo), solo button.
        Line thickness/style are in the right-click chart context menu."""
        for w in self._legend_frame.winfo_children():
            w.destroy()

        self._solo_btns: Dict[str, ctk.CTkButton] = {}

        if not self._targets:
            return

        hint = ctk.CTkLabel(
            self._legend_frame,
            text="🎨 swatch = color  ·  👁 = isolate  ·  right-click chart = line properties",
            font=(FONT_FAMILY, FONT_SIZE_TINY),
            text_color=TEXT_MUTED,
        )
        hint.pack(side="right", padx=(0, 4))

        for t in self._targets:
            item = ctk.CTkFrame(self._legend_frame, fg_color="transparent")
            item.pack(side="left", padx=(0, 8))

            # ── Color swatch ──
            swatch = ctk.CTkFrame(item, fg_color=t.color, corner_radius=4,
                                   width=22, height=20, cursor="hand2")
            swatch.pack(side="left", padx=(0, 4))
            swatch.pack_propagate(False)
            ip_ref = t.ip
            swatch.bind("<Button-1>", lambda e, ip=ip_ref: self._pick_color(ip))
            t._swatch_widget = swatch  # type: ignore[attr-defined]

            # ── Device name (click to solo) ──
            lbl = ctk.CTkLabel(item, text=t.display_name,
                                font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                                text_color=TEXT_PRIMARY, cursor="hand2")
            lbl.pack(side="left", padx=(0, 3))
            lbl.bind("<Button-1>", lambda e, ip=ip_ref: self._toggle_solo(ip))

            # ── Solo button ──
            is_solo = (self._solo_ip == t.ip)
            solo_btn = ctk.CTkButton(
                item, text="👁", font=(FONT_FAMILY, 11),
                width=24, height=20,
                fg_color=SAS_ORANGE if is_solo else BG_MEDIUM,
                hover_color=SAS_ORANGE_DARK, text_color="white",
                corner_radius=4,
                command=lambda ip=ip_ref: self._toggle_solo(ip),
            )
            solo_btn.pack(side="left", padx=(0, 4))
            self._solo_btns[t.ip] = solo_btn

    def _on_line_width_change(self, ip: str, label: str):
        self._line_prefs.setdefault(ip, self._default_line_pref())["width"] = self.WIDTH_OPTIONS.get(label, 1.5)
        self._draw_chart()

    def _on_line_dash_change(self, ip: str, label: str):
        self._line_prefs.setdefault(ip, self._default_line_pref())["dash"] = self.DASH_STYLES.get(label, ())
        self._draw_chart()

    def _on_chart_right_click(self, event):
        """Show a context menu for chart line properties on right-click."""
        if not self._targets:
            return
        menu = tk.Menu(self, tearoff=0,
                       bg=resolve_color(BG_MEDIUM),
                       fg=resolve_color(TEXT_PRIMARY),
                       activebackground=resolve_color(SAS_BLUE),
                       activeforeground="white",
                       font=(FONT_FAMILY, 10))
        menu.add_command(label="📐  Line Properties…",
                         command=self._open_line_properties_dialog,
                         state="normal")
        menu.add_separator()
        for t in self._targets:
            menu.add_command(
                label=f"   {t.display_name}  ({t.ip})",
                command=lambda ip=t.ip: self._open_line_properties_dialog(ip),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_line_properties_dialog(self, target_ip: Optional[str] = None):
        """Open a CTkToplevel dialog to edit line thickness and style for devices."""
        if not self._targets:
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Line Properties")
        dlg.resizable(False, False)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="Chart Line Properties",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(padx=20, pady=(16, 4))
        ctk.CTkLabel(dlg,
                     text="Adjust thickness and style for each device's trend line.",
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(padx=20, pady=(0, 12))

        body = ctk.CTkFrame(dlg, fg_color=resolve_color(BG_MEDIUM), corner_radius=8)
        body.pack(fill="x", padx=20, pady=(0, 8))

        # Column headers
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        for txt, w in [("Device", 160), ("Color", 60), ("Thickness", 100), ("Style", 90)]:
            ctk.CTkLabel(hdr, text=txt, width=w,
                         font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                         text_color=TEXT_SECONDARY, anchor="w").pack(side="left", padx=4)

        _w_vars: Dict[str, ctk.StringVar] = {}
        _d_vars: Dict[str, ctk.StringVar] = {}

        for t in self._targets:
            prefs = self._line_prefs.setdefault(t.ip, self._default_line_pref())
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)

            # Device name
            ctk.CTkLabel(row, text=t.display_name, width=160,
                         font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                         text_color=t.color, anchor="w").pack(side="left", padx=4)

            # Color swatch (click to pick)
            swatch = ctk.CTkFrame(row, fg_color=t.color, corner_radius=4,
                                   width=30, height=22, cursor="hand2")
            swatch.pack(side="left", padx=4)
            swatch.pack_propagate(False)
            ip_ref = t.ip
            swatch.bind("<Button-1>", lambda e, ip=ip_ref, sw=swatch: self._dlg_pick_color(ip, sw))

            # Thickness dropdown
            rev_width = {v: k for k, v in self.WIDTH_OPTIONS.items()}
            w_var = ctk.StringVar(value=rev_width.get(prefs["width"], "2px"))
            _w_vars[t.ip] = w_var
            ctk.CTkOptionMenu(
                row, variable=w_var,
                values=list(self.WIDTH_OPTIONS.keys()),
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                fg_color=resolve_color(BG_DARK), button_color=SAS_BLUE,
                button_hover_color=SAS_BLUE_DARK, dropdown_fg_color=resolve_color(BG_MEDIUM),
                text_color=TEXT_PRIMARY, width=95, height=26,
            ).pack(side="left", padx=4)

            # Style dropdown
            rev_dash = {v: k for k, v in self.DASH_STYLES.items()}
            d_var = ctk.StringVar(value=rev_dash.get(prefs["dash"], "Solid"))
            _d_vars[t.ip] = d_var
            ctk.CTkOptionMenu(
                row, variable=d_var,
                values=list(self.DASH_STYLES.keys()),
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                fg_color=resolve_color(BG_DARK), button_color=SAS_BLUE,
                button_hover_color=SAS_BLUE_DARK, dropdown_fg_color=resolve_color(BG_MEDIUM),
                text_color=TEXT_PRIMARY, width=85, height=26,
            ).pack(side="left", padx=4)

        # Focus on a specific device if requested
        if target_ip:
            pass  # Future: scroll to / highlight that row

        # Buttons
        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 16))

        def _apply():
            for ip in _w_vars:
                p = self._line_prefs.setdefault(ip, self._default_line_pref())
                p["width"] = self.WIDTH_OPTIONS.get(_w_vars[ip].get(), 1.5)
                p["dash"]  = self.DASH_STYLES.get(_d_vars[ip].get(), ())
            self._draw_chart()
            dlg.destroy()

        ctk.CTkButton(btn_row, text="✔ Apply", width=100, height=BUTTON_HEIGHT,
                      fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
                      font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
                      command=_apply).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Cancel", width=90, height=BUTTON_HEIGHT,
                      fg_color="transparent", border_width=1, border_color=BORDER_COLOR,
                      text_color=TEXT_SECONDARY, hover_color=BG_CARD_HOVER,
                      font=(FONT_FAMILY, FONT_SIZE_BODY),
                      command=dlg.destroy).pack(side="right")

    def _dlg_pick_color(self, ip: str, swatch_widget):
        """Color picker called from inside the properties dialog."""
        from tkinter import colorchooser
        target = next((t for t in self._targets if t.ip == ip), None)
        if not target:
            return
        result = colorchooser.askcolor(color=target.color,
                                        title=f"Color — {target.display_name}")
        if result and result[1]:
            target.color = result[1]
            swatch_widget.configure(fg_color=result[1])
            if hasattr(target, "_swatch_widget"):
                try:
                    target._swatch_widget.configure(fg_color=result[1])
                except Exception:
                    pass
            for mt in self._monitor.targets:
                if mt.ip == ip:
                    mt.color = result[1]
            self._draw_chart()
        """Open a color chooser for the given device and update its chart line color."""
        from tkinter import colorchooser

        target = next((t for t in self._targets if t.ip == ip), None)
        if not target:
            return

        result = colorchooser.askcolor(
            color=target.color,
            title=f"Choose color for {target.display_name}",
            parent=self,
        )

        # result = ((r, g, b), '#rrggbb') or (None, None) if cancelled
        if result and result[1]:
            new_color = result[1]
            target.color = new_color

            # Update swatch widget background live
            if hasattr(target, "_swatch_widget"):
                try:
                    target._swatch_widget.configure(fg_color=new_color)
                except Exception:
                    pass

            # Also update the monitor engine's target color
            for mt in self._monitor.targets:
                if mt.ip == ip:
                    mt.color = new_color

            self._draw_chart()

    def _toggle_solo(self, ip: str):
        """Toggle isolated/solo mode for a device. Click again to return to all-devices view."""
        if self._solo_ip == ip:
            # Already soloed — go back to all-devices view
            self._show_all_devices()
        else:
            self._solo_ip = ip
            target = next((t for t in self._targets if t.ip == ip), None)
            name = target.display_name if target else ip

            # Update solo label
            self._solo_label.configure(text=f"● Isolated: {name}")

            # Show "Show All" button in the chart header controls
            self._show_all_btn.pack(side="left", padx=(0, 8))

            # Update solo button styles in legend
            for tip, btn in self._solo_btns.items():
                btn.configure(fg_color=SAS_ORANGE if tip == ip else BG_MEDIUM)

            self._draw_chart()

    def _show_all_devices(self):
        """Return from solo mode to showing all devices."""
        self._solo_ip = None
        self._solo_label.configure(text="")
        self._show_all_btn.pack_forget()

        # Reset all solo button styles
        for btn in self._solo_btns.values():
            btn.configure(fg_color=BG_MEDIUM)

        self._draw_chart()

    # ── Analysis Section ─────────────────────────────────────────────────────

    def _build_analysis_section(self, parent):
        """Build the collapsible analysis results section."""
        self._analysis_card = ctk.CTkFrame(
            parent, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        self._analysis_card.pack(fill="x", pady=(0, 10))

        hdr = ctk.CTkFrame(self._analysis_card, fg_color="transparent")
        hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))

        ctk.CTkLabel(hdr, text="🔍  Diagnostic Analysis",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        ctk.CTkLabel(hdr,
                     text="Click 'Analyze' to run diagnostics on collected data",
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(side="left", padx=(14, 0))

        self._analysis_hint_lbl = ctk.CTkLabel(
            hdr, text="",
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
            text_color=SAS_BLUE_LIGHT)
        self._analysis_hint_lbl.pack(side="right")

        self._analysis_body = ctk.CTkFrame(self._analysis_card, fg_color="transparent")
        self._analysis_body.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

        ctk.CTkLabel(self._analysis_body,
                     text="Collect data, then click  🔍 Analyze  to generate findings.",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_MUTED).pack(pady=10)

    def _run_analysis(self):
        """Run multi-device analysis using MonitorAnalyzer for each device."""
        from core.monitor_analyzer import MonitorAnalyzer
        if not self._targets:
            return

        self._analyze_btn.configure(state="disabled", text="⏳ Analyzing…")

        samples   = self._monitor.samples
        outages   = self._monitor.outages
        analytics = self._monitor.get_analytics()

        def _analyze_thread():
            analyzer = MonitorAnalyzer()
            reports = {}
            for t in self._targets:
                stats = analytics.get(t.ip)
                try:
                    report = analyzer.analyze(samples, outages, stats, t.ip)
                    reports[t.ip] = report
                except Exception as e:
                    logger.error(f"Analysis failed for {t.ip}: {e}")
            self.after(0, lambda: self._display_analysis(reports))

        threading.Thread(target=_analyze_thread, daemon=True).start()

    def _display_analysis(self, reports: dict):
        """Render analysis reports for all devices."""
        self._analyze_btn.configure(state="normal", text="🔍 Analyze")
        self._analysis_reports = reports  # Store for PDF export

        for w in self._analysis_body.winfo_children():
            w.destroy()

        if not reports:
            ctk.CTkLabel(self._analysis_body, text="No analysis data available.",
                         font=(FONT_FAMILY, FONT_SIZE_BODY),
                         text_color=TEXT_MUTED).pack(pady=10)
            return

        total_findings = sum(len(r.findings) for r in reports.values())
        critical = sum(1 for r in reports.values()
                       for f in r.findings if f.severity == "critical")
        warn = sum(1 for r in reports.values()
                   for f in r.findings if f.severity == "warning")

        summary_color = STATUS_ERROR if critical else (STATUS_WARN if warn else STATUS_GOOD)
        summary_txt = (f"Found {total_findings} finding(s) across {len(reports)} device(s)"
                       if total_findings else "✅ No issues detected across all monitored devices.")
        self._analysis_hint_lbl.configure(text=summary_txt, text_color=summary_color)

        from ui.widgets import FindingCard

        for t in self._targets:
            report = reports.get(t.ip)
            if not report:
                continue

            target = next((tg for tg in self._targets if tg.ip == t.ip), None)
            dev_label = target.display_name if target else t.ip

            # Device sub-header
            drow = ctk.CTkFrame(self._analysis_body, fg_color="transparent")
            drow.pack(fill="x", pady=(8, 4))

            swatch = ctk.CTkFrame(drow, fg_color=target.color if target else SAS_BLUE,
                                   corner_radius=3, width=12, height=12)
            swatch.pack(side="left", padx=(0, 6))
            swatch.pack_propagate(False)

            ctk.CTkLabel(drow, text=dev_label,
                         font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
                         text_color=TEXT_PRIMARY).pack(side="left")

            score_c = STATUS_GOOD if report.health_score >= 80 else (
                STATUS_WARN if report.health_score >= 60 else STATUS_ERROR)
            ctk.CTkLabel(drow, text=f"  Health: {report.health_score}/100  {report.health_label}",
                         font=(FONT_FAMILY, FONT_SIZE_SMALL),
                         text_color=score_c).pack(side="left", padx=(8, 0))

            if not report.findings:
                ctk.CTkLabel(self._analysis_body,
                             text=f"   ✅ No issues found for {dev_label}",
                             font=(FONT_FAMILY, FONT_SIZE_SMALL),
                             text_color=STATUS_GOOD).pack(anchor="w", padx=(16, 0), pady=2)
                continue

            for finding in report.findings:
                FindingCard(
                    self._analysis_body,
                    title=finding.title,
                    severity=finding.severity,
                    summary=finding.description,
                    explanation=finding.likely_cause,
                    recommendation=finding.suggestion,
                    raw_value=finding.metric_value,
                ).pack(fill="x", pady=(0, 6))

    # ── Analytics Table Update ───────────────────────────────────────────────

    def _update_analytics_table(self):
        analytics = self._monitor.get_analytics()

        for item in self._analytics_tree.get_children():
            self._analytics_tree.delete(item)

        for t in self._targets:
            a = analytics.get(t.ip)
            if not a:
                continue

            # Determine row tag: offline > high jitter (warn) > online
            if a.last_status == "offline":
                tag = "offline"
            elif a.ping_jitter_ms > 20:
                tag = "warn"
            elif a.last_status == "online":
                tag = "online"
            else:
                tag = "unknown"

            if a.longest_outage_sec > 0:
                s = a.longest_outage_sec
                longest = f"{int(s//60)}m {int(s%60):02d}s" if s >= 60 else f"{s:.1f}s"
            else:
                longest = "—"

            self._analytics_tree.insert("", "end", values=(
                t.display_name,
                a.last_status.upper(),
                f"{a.uptime_pct:.1f}%",
                f"{a.ping_avg_ms:.1f}ms"    if a.ping_avg_ms    > 0 else "—",
                f"{a.ping_min_ms:.1f}ms"    if a.ping_min_ms    > 0 else "—",
                f"{a.ping_max_ms:.1f}ms"    if a.ping_max_ms    > 0 else "—",
                f"{a.ping_jitter_ms:.1f}ms" if a.ping_jitter_ms > 0 else "—",
                f"{a.ping_loss_pct:.1f}%",
                f"{a.cip_avg_ms:.1f}ms"     if a.cip_avg_ms     > 0 else "—",
                str(a.outage_count),
                longest,
                a.product_name or "—",
            ), tags=(tag,))

    # ── Live Update Loop ─────────────────────────────────────────────────────

    def _on_new_sample(self, sample: MultiPollSample):
        self._trend_timestamps.append(sample.timestamp)
        for t in self._targets:
            vals = self._trend_values.setdefault(t.ip, [])
            result = sample.results.get(t.ip)
            vals.append(result.ping_time_ms if (result and result.ping_success) else None)

    def _update_display(self):
        if not self._running:
            return

        self._draw_chart()

        count   = self._monitor.sample_count
        elapsed = self._monitor.elapsed_seconds
        if elapsed < 60:
            dur = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            dur = f"{int(elapsed//60)}m {int(elapsed%60):02d}s"
        else:
            dur = f"{int(elapsed//3600)}h {int((elapsed%3600)//60):02d}m"
        self._chart_points_label.configure(text=f"{count:,} samples  •  {dur}")

        self._update_analytics_table()

        if self._running:
            self._chart_timer = self.after(1000, self._update_display)

    # ── Start / Stop ─────────────────────────────────────────────────────────

    def _toggle_monitor(self):
        if self._running:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _parse_ips(self, raw: str) -> List[str]:
        ips = []
        for part in raw.replace(",", " ").replace(";", " ").split():
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                try:
                    pieces = part.split("-", 1)
                    start_str, end_str = pieces[0].strip(), pieces[1].strip()
                    start_addr = ipaddress.IPv4Address(start_str)
                    try:
                        end_addr = ipaddress.IPv4Address(end_str)
                    except ipaddress.AddressValueError:
                        octets = start_str.split(".")
                        octets[-1] = end_str
                        end_addr = ipaddress.IPv4Address(".".join(octets))
                    if int(end_addr) >= int(start_addr):
                        cur = int(start_addr)
                        while cur <= int(end_addr):
                            ips.append(str(ipaddress.IPv4Address(cur)))
                            cur += 1
                    else:
                        ips.append(part)
                except Exception:
                    ips.append(part)
            else:
                ips.append(part)
        return ips

    def _start_monitor(self):
        raw = self._ip_entry.get().strip()
        if not raw:
            self._status_label.configure(text="⚠ Enter at least one IP address",
                                          text_color=STATUS_WARN)
            return

        ips = self._parse_ips(raw)
        if not ips:
            self._status_label.configure(text="⚠ No valid IPs found",
                                          text_color=STATUS_WARN)
            return

        rate_str = self._rate_var.get()
        rate = float(rate_str.replace("ms","").strip())/1000.0 if "ms" in rate_str \
               else float(rate_str.replace("sec","").strip())

        try:
            timeout = float(self._timeout_entry.get()) / 1000.0
        except ValueError:
            timeout = 2.0

        self._targets = [
            DeviceTarget(ip=ip, color=CHART_COLORS[i % len(CHART_COLORS)])
            for i, ip in enumerate(ips)
        ]

        self._trend_values    = {}
        self._trend_timestamps = []
        self._event_markers   = []

        # Reset solo mode for the new session
        self._solo_ip = None
        self._show_all_btn.pack_forget()
        self._solo_label.configure(text="")

        # Reset line prefs to defaults for new target list
        self._line_prefs = {}

        # Reset stacked canvases (will be rebuilt when needed)
        self._stacked_canvases.clear()
        if self._stacked.get():
            self._rebuild_stacked_canvases()

        # Clear log
        self._status_log_text.configure(state="normal")
        self._status_log_text.delete("1.0", "end")
        self._status_log_text.configure(state="disabled")

        self._monitor.clear()
        self._monitor.set_targets(self._targets)
        self._monitor.set_poll_interval(rate)
        self._monitor.set_timeout(timeout)
        self._monitor.set_on_sample(lambda s: self.after(0, lambda: self._on_new_sample(s)))
        self._monitor.set_on_device_status(self._on_device_status_change)

        self._build_legend()
        self._draw_empty_chart()

        self._monitor.start()
        self._running = True



        self._ip_entry.configure(state="disabled")
        self._start_btn.configure(text="■ Stop Monitor", fg_color=STATUS_ERROR,
                                   hover_color="#b91c1c")
        self._mark_btn.configure(state="normal")
        self._export_btn.configure(state="normal")
        self._csv_btn.configure(state="normal")
        self._analyze_btn.configure(state="normal")
        self._status_label.configure(
            text=f"⬤ Monitoring {len(ips)} device(s) at {rate_str}  |  "
                 f"Avg line + Min/Max band enabled",
            text_color=STATUS_GOOD)

        self._chart_timer = self.after(1000, self._update_display)

    def _stop_monitor(self):
        self._running = False
        self._monitor.stop()

        if self._chart_timer:
            self.after_cancel(self._chart_timer)
            self._chart_timer = None

        self._draw_chart()
        self._update_analytics_table()

        count   = self._monitor.sample_count
        elapsed = self._monitor.elapsed_seconds
        if elapsed < 60:
            dur = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            dur = f"{int(elapsed//60)}m {int(elapsed%60):02d}s"
        else:
            dur = f"{int(elapsed//3600)}h {int((elapsed%3600)//60):02d}m"
        self._chart_points_label.configure(text=f"{count:,} samples  •  {dur}")



        self._ip_entry.configure(state="normal")
        self._mark_btn.configure(state="disabled")
        self._start_btn.configure(text="▶ Start Monitor", fg_color=SAS_BLUE,
                                   hover_color=SAS_BLUE_DARK)
        # Keep Analyze and Export active so user can analyze/export after stopping
        self._status_label.configure(
            text=f"Monitoring stopped — {count:,} samples collected over {elapsed:.0f}s",
            text_color=TEXT_SECONDARY)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"MultiMonitor_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv",
        )
        if not filepath:
            return
        ok, msg = self._monitor.export_csv(filepath)
        color = STATUS_GOOD if ok else STATUS_ERROR
        text  = f"✅ CSV exported: {os.path.basename(filepath)}" if ok else f"❌ Export failed: {msg}"
        self._status_label.configure(text=text, text_color=color)

    def _export_report(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=f"MultiMonitor_Report_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.pdf",
        )
        if not filepath:
            return

        self._status_label.configure(text="⏳ Generating PDF report...",
                                      text_color=SAS_BLUE_LIGHT)

        def generate():
            try:
                chart_img_path = None
                try:
                    chart_img_path = os.path.join(
                        os.path.expanduser("~"), ".sas-netdiag", "_multi_chart.png")
                    os.makedirs(os.path.dirname(chart_img_path), exist_ok=True)
                    self._chart_canvas.update_idletasks()
                    ps_path = chart_img_path.replace(".png", ".eps")
                    self._chart_canvas.postscript(file=ps_path, colormode="color")
                    try:
                        from PIL import Image as PILImage
                        img = PILImage.open(ps_path)
                        img.save(chart_img_path, "PNG")
                    except Exception:
                        chart_img_path = None
                except Exception:
                    chart_img_path = None

                from core.pdf_report import generate_multi_monitor_report
                result_path = generate_multi_monitor_report(
                    targets=self._targets,
                    analytics=self._monitor.get_analytics(),
                    elapsed_seconds=self._monitor.elapsed_seconds,
                    sample_count=self._monitor.sample_count,
                    chart_image_path=chart_img_path,
                    analysis_reports=self._analysis_reports or None,
                    output_path=filepath,
                )
                self.after(0, lambda: self._status_label.configure(
                    text=f"✅ Report saved: {os.path.basename(result_path)}",
                    text_color=STATUS_GOOD))
            except Exception as e:
                logger.error(f"Report export failed: {e}", exc_info=True)
                self.after(0, lambda: self._status_label.configure(
                    text=f"❌ Report failed: {e}", text_color=STATUS_ERROR))

        threading.Thread(target=generate, daemon=True).start()
