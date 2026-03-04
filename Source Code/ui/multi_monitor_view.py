"""
SAS Network Diagnostic Tool — Multi-Device Monitor View
Monitor multiple Ethernet devices simultaneously with a real-time trend chart
and analytics table.  Chart is pure tkinter Canvas — no external dependencies.
"""

import ipaddress
import logging
import math
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime
from typing import Dict, List, Optional

import customtkinter as ctk

from core.multi_monitor import (
    MultiDeviceMonitor, DeviceTarget, DeviceAnalytics,
    MultiPollSample, CHART_COLORS,
)
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)

# ── Chart layout constants ───────────────────────────────────────────────────
CHART_HEIGHT      = 260
CHART_LEFT_MARGIN = 52
CHART_RIGHT_MARGIN = 16
CHART_TOP_MARGIN   = 10
CHART_BOTTOM_MARGIN = 22
CHART_VISIBLE     = 200          # Max points shown in viewport


def resolve_color(c):
    """Resolve CustomTkinter color tuples to a single hex string."""
    if isinstance(c, (list, tuple)):
        return c[1]  # dark mode
    return c


class MultiMonitorView(ctk.CTkFrame):
    """Monitor multiple devices with live trend chart and analytics."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._monitor = MultiDeviceMonitor()
        self._targets: List[DeviceTarget] = []
        self._running = False
        self._chart_timer = None
        self._chart_last_w = 800

        # Per-device data arrays: {ip: [val_or_None, ...]}
        self._trend_values: Dict[str, List[Optional[float]]] = {}
        self._trend_timestamps: List[datetime] = []

        self._build_ui()

    def on_show(self):
        pass

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
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

        self._csv_btn = ctk.CTkButton(
            btn_frame, text="📋 Export CSV",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=BG_CARD_HOVER, width=120, height=BUTTON_HEIGHT,
            command=self._export_csv, state="disabled",
        )
        self._csv_btn.pack(side="left")

        # ── Config Card ──────────────────────────────────────────────────────
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
            width=420, height=BUTTON_HEIGHT,
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

        # ── Scrollable content ───────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._scroll.pack(fill="both", expand=True, padx=20, pady=(8, 20))
        enable_touch_scroll(self._scroll)

        # ── Trend Chart Card ─────────────────────────────────────────────────
        chart_card = ctk.CTkFrame(
            self._scroll, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
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
        self._chart_points_label.pack(side="right")

        # Canvas chart
        self._chart_canvas = tk.Canvas(
            chart_card, height=CHART_HEIGHT,
            bg=resolve_color(BG_DARK),
            highlightthickness=0, bd=0,
        )
        self._chart_canvas.pack(fill="x", padx=8, pady=(4, 4))
        self._chart_canvas.bind("<Configure>", self._on_chart_resize)

        # Legend
        self._legend_frame = ctk.CTkFrame(chart_card, fg_color="transparent")
        self._legend_frame.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

        self._draw_empty_chart()

        # ── Analytics Table Card ─────────────────────────────────────────────
        table_card = ctk.CTkFrame(
            self._scroll, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        table_card.pack(fill="x", pady=(0, 10))

        table_hdr = ctk.CTkFrame(table_card, fg_color="transparent")
        table_hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))
        ctk.CTkLabel(table_hdr, text="Device Analytics",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        self._build_analytics_table(table_card)

    # ── Canvas Chart Drawing ─────────────────────────────────────────────────

    def _on_chart_resize(self, event):
        if event.width > 50:
            self._chart_last_w = event.width
            self._draw_chart()

    def _draw_empty_chart(self):
        c = self._chart_canvas
        c.delete("all")
        w = self._chart_last_w
        h = CHART_HEIGHT
        px0 = CHART_LEFT_MARGIN
        px1 = w - CHART_RIGHT_MARGIN
        py0 = CHART_TOP_MARGIN
        py1 = h - CHART_BOTTOM_MARGIN

        for frac in [0.25, 0.5, 0.75]:
            y = py0 + int((py1 - py0) * frac)
            c.create_line(px0, y, px1, y, fill=resolve_color(BORDER_COLOR), dash=(2, 4))

        c.create_text(w // 2, h // 2,
                       text="Start monitoring to see response times",
                       fill=resolve_color(TEXT_MUTED), font=(FONT_FAMILY, 11))

    def _draw_chart(self):
        """Redraw the multi-device trend chart."""
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

        # Viewport: show last CHART_VISIBLE points
        end = total_pts
        start = max(0, end - CHART_VISIBLE)
        n_points = end - start

        px0 = CHART_LEFT_MARGIN
        px1 = w - CHART_RIGHT_MARGIN
        py0 = CHART_TOP_MARGIN
        py1 = h - CHART_BOTTOM_MARGIN
        pw = px1 - px0
        ph = py1 - py0

        if pw < 20 or ph < 20:
            return

        # ── Y-axis auto-scale from visible data ──
        all_vals = []
        for t in self._targets:
            vals = self._trend_values.get(t.ip, [])
            for v in vals[start:end]:
                if v is not None:
                    all_vals.append(v)

        if not all_vals:
            max_val = 10.0
        else:
            max_val = max(all_vals) * 1.15
            max_val = max(max_val, 1.0)

        # Snap to nice values
        nice = [2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
        for n in nice:
            if max_val <= n:
                max_val = n
                break
        else:
            max_val = math.ceil(max_val / 500) * 500

        # ── Grid + Y labels ──
        grid_c = resolve_color(BORDER_COLOR)
        text_c = resolve_color(TEXT_MUTED)

        for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = py0 + int(ph * frac)
            c.create_line(px0, y, px1, y, fill=grid_c, dash=(2, 4))
            val = max_val * (1.0 - frac)
            if val >= 100:
                lbl = f"{val:.0f}"
            elif val >= 1:
                lbl = f"{val:.1f}"
            else:
                lbl = f"{val:.2f}"
            c.create_text(px0 - 4, y, text=lbl, fill=text_c,
                           anchor="e", font=("Consolas", 8))

        c.create_text(px0 - 4, py0 - 8, text="ms", fill=text_c,
                       anchor="e", font=("Consolas", 8))

        # ── X-axis time labels ──
        x_step = pw / max(n_points - 1, 1)
        timestamps = self._trend_timestamps[start:end]

        label_count = min(6, n_points)
        label_step = max(1, n_points // label_count)
        for idx in range(0, n_points, label_step):
            x = px0 + idx * x_step
            if idx < len(timestamps):
                ts = timestamps[idx].strftime("%H:%M:%S")
                c.create_text(x, py1 + 10, text=ts, fill=text_c,
                               anchor="n", font=("Consolas", 7))

        # ── Plot each device as a line ──
        for t in self._targets:
            vals = self._trend_values.get(t.ip, [])
            data = vals[start:end]
            if not data:
                continue

            points = []
            for i, val in enumerate(data):
                x = px0 + i * x_step
                if val is not None and max_val > 0:
                    y = py0 + ph * (1.0 - val / max_val)
                    y = max(py0, min(py1, y))
                    points.append((x, y))
                else:
                    # Fail marker
                    c.create_rectangle(x - 2, py1 - 5, x + 2, py1 - 1,
                                        fill="#EF4444", outline="")
                    # Break line at failure
                    if len(points) >= 2:
                        flat = [coord for p in points for coord in p]
                        c.create_line(*flat, fill=t.color, width=1.5, smooth=True)
                    points = []

            if len(points) >= 2:
                flat = [coord for p in points for coord in p]
                c.create_line(*flat, fill=t.color, width=1.5, smooth=True)

    # ── Legend ────────────────────────────────────────────────────────────────

    def _build_legend(self):
        for w in self._legend_frame.winfo_children():
            w.destroy()

        for t in self._targets:
            item = ctk.CTkFrame(self._legend_frame, fg_color="transparent")
            item.pack(side="left", padx=(0, 16))

            swatch = tk.Canvas(item, width=12, height=12, bd=0,
                               highlightthickness=0,
                               bg=resolve_color(BG_CARD))
            swatch.create_rectangle(1, 1, 11, 11, fill=t.color, outline=t.color)
            swatch.pack(side="left", padx=(0, 4))

            ctk.CTkLabel(item, text=t.display_name,
                         font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                         text_color=TEXT_PRIMARY).pack(side="left")

    # ── Analytics Table ──────────────────────────────────────────────────────

    def _build_analytics_table(self, parent):
        tree_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tree_frame.pack(fill="x", padx=8, pady=(0, 8))

        columns = ("ip", "status", "uptime", "ping_avg", "ping_min", "ping_max",
                    "ping_loss", "cip_avg", "outages", "longest", "product")
        col_names = {
            "ip": "IP Address", "status": "Status", "uptime": "Uptime %",
            "ping_avg": "Ping Avg", "ping_min": "Ping Min", "ping_max": "Ping Max",
            "ping_loss": "Ping Loss %", "cip_avg": "CIP Avg",
            "outages": "Outages", "longest": "Longest", "product": "Product",
        }
        col_widths = {
            "ip": 130, "status": 70, "uptime": 75, "ping_avg": 80,
            "ping_min": 75, "ping_max": 75, "ping_loss": 80, "cip_avg": 75,
            "outages": 65, "longest": 80, "product": 160,
        }

        bg_color = resolve_color(BG_DARK)
        fg_color = resolve_color(TEXT_PRIMARY)
        hdr_bg = resolve_color(BG_MEDIUM)
        sel_bg = resolve_color(SAS_BLUE)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Multi.Treeview",
                         background=bg_color,
                         foreground=fg_color,
                         fieldbackground=bg_color,
                         font=(FONT_FAMILY, 10),
                         rowheight=28,
                         borderwidth=0)
        style.configure("Multi.Treeview.Heading",
                         background=hdr_bg,
                         foreground=fg_color,
                         font=(FONT_FAMILY, 10, "bold"),
                         borderwidth=1,
                         relief="flat")
        style.map("Multi.Treeview.Heading",
                   background=[("active", hdr_bg)])
        style.map("Multi.Treeview",
                   background=[("selected", sel_bg)],
                   foreground=[("selected", "#FFFFFF")])

        self._analytics_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            style="Multi.Treeview", height=8,
        )

        for col in columns:
            self._analytics_tree.heading(col, text=col_names[col])
            self._analytics_tree.column(col, width=col_widths.get(col, 80),
                                         minwidth=50, anchor="center")
        self._analytics_tree.column("ip", anchor="w")
        self._analytics_tree.column("product", anchor="w")

        scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                                command=self._analytics_tree.yview)
        self._analytics_tree.configure(yscrollcommand=scroll.set)

        self._analytics_tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")

        self._analytics_tree.tag_configure("online", foreground="#22C55E")
        self._analytics_tree.tag_configure("offline", foreground="#EF4444")
        self._analytics_tree.tag_configure("unknown", foreground=resolve_color(TEXT_MUTED))

    def _update_analytics_table(self):
        analytics = self._monitor.get_analytics()

        for item in self._analytics_tree.get_children():
            self._analytics_tree.delete(item)

        for t in self._targets:
            a = analytics.get(t.ip)
            if not a:
                continue

            status = a.last_status
            tag = status

            if a.longest_outage_sec > 0:
                if a.longest_outage_sec < 60:
                    longest = f"{a.longest_outage_sec:.1f}s"
                else:
                    longest = f"{int(a.longest_outage_sec // 60)}m {int(a.longest_outage_sec % 60):02d}s"
            else:
                longest = "—"

            self._analytics_tree.insert("", "end", values=(
                t.display_name,
                status.upper(),
                f"{a.uptime_pct:.1f}%",
                f"{a.ping_avg_ms:.1f}ms" if a.ping_avg_ms > 0 else "—",
                f"{a.ping_min_ms:.1f}ms" if a.ping_min_ms > 0 else "—",
                f"{a.ping_max_ms:.1f}ms" if a.ping_max_ms > 0 else "—",
                f"{a.ping_loss_pct:.1f}%",
                f"{a.cip_avg_ms:.1f}ms" if a.cip_avg_ms > 0 else "—",
                str(a.outage_count),
                longest,
                a.product_name or "—",
            ), tags=(tag,))

    # ── Live Update Loop ─────────────────────────────────────────────────────

    def _on_new_sample(self, sample: MultiPollSample):
        """Called by monitor engine on each poll — append data to arrays."""
        self._trend_timestamps.append(sample.timestamp)
        for t in self._targets:
            vals = self._trend_values.setdefault(t.ip, [])
            result = sample.results.get(t.ip)
            if result and result.ping_success:
                vals.append(result.ping_time_ms)
            else:
                vals.append(None)

    def _update_display(self):
        """Periodic UI refresh: chart + table + labels."""
        if not self._running:
            return

        # Redraw chart
        self._draw_chart()

        # Update labels
        count = self._monitor.sample_count
        elapsed = self._monitor.elapsed_seconds
        if elapsed < 60:
            dur = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            dur = f"{int(elapsed // 60)}m {int(elapsed % 60):02d}s"
        else:
            dur = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60):02d}m"
        self._chart_points_label.configure(text=f"{count:,} samples  •  {dur}")

        # Update table
        self._update_analytics_table()

        # Schedule next
        if self._running:
            self._chart_timer = self.after(1000, self._update_display)

    # ── Start / Stop ─────────────────────────────────────────────────────────

    def _toggle_monitor(self):
        if self._running:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _parse_ips(self, raw: str) -> List[str]:
        """Parse IP input — supports ranges, shorthand, comma/space separated."""
        ips = []
        for part in raw.replace(",", " ").replace(";", " ").split():
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                try:
                    pieces = part.split("-", 1)
                    start_str = pieces[0].strip()
                    end_str = pieces[1].strip()

                    start_addr = ipaddress.IPv4Address(start_str)

                    # Shorthand: 192.168.27.110-120
                    try:
                        end_addr = ipaddress.IPv4Address(end_str)
                    except ipaddress.AddressValueError:
                        octets = start_str.split(".")
                        octets[-1] = end_str
                        end_addr = ipaddress.IPv4Address(".".join(octets))

                    if int(end_addr) < int(start_addr):
                        ips.append(part)
                        continue

                    current = int(start_addr)
                    end_int = int(end_addr)
                    while current <= end_int:
                        ips.append(str(ipaddress.IPv4Address(current)))
                        current += 1
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

        # Parse rate
        rate_str = self._rate_var.get()
        if "ms" in rate_str:
            rate = float(rate_str.replace("ms", "").strip()) / 1000.0
        else:
            rate = float(rate_str.replace("sec", "").strip())

        # Parse timeout
        try:
            timeout = float(self._timeout_entry.get()) / 1000.0
        except ValueError:
            timeout = 2.0

        # Build targets
        self._targets = []
        for i, ip in enumerate(ips):
            t = DeviceTarget(ip=ip, color=CHART_COLORS[i % len(CHART_COLORS)])
            self._targets.append(t)

        # Clear data arrays
        self._trend_values = {}
        self._trend_timestamps = []

        # Configure engine
        self._monitor.clear()
        self._monitor.set_targets(self._targets)
        self._monitor.set_poll_interval(rate)
        self._monitor.set_timeout(timeout)
        self._monitor.set_on_sample(lambda s: self.after(0, lambda: self._on_new_sample(s)))

        self._build_legend()
        self._draw_empty_chart()

        self._monitor.start()
        self._running = True

        # UI state
        self._ip_entry.configure(state="disabled")
        self._start_btn.configure(text="■ Stop Monitor", fg_color=STATUS_ERROR,
                                   hover_color="#b91c1c")
        self._export_btn.configure(state="normal")
        self._csv_btn.configure(state="normal")
        self._status_label.configure(
            text=f"⬤ Monitoring {len(ips)} device(s) at {rate_str}",
            text_color=STATUS_GOOD)

        self._chart_timer = self.after(1000, self._update_display)

    def _stop_monitor(self):
        self._running = False
        self._monitor.stop()

        if self._chart_timer:
            self.after_cancel(self._chart_timer)
            self._chart_timer = None

        # Final redraw
        self._draw_chart()
        self._update_analytics_table()

        count = self._monitor.sample_count
        elapsed = self._monitor.elapsed_seconds
        if elapsed < 60:
            dur = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            dur = f"{int(elapsed // 60)}m {int(elapsed % 60):02d}s"
        else:
            dur = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60):02d}m"
        self._chart_points_label.configure(text=f"{count:,} samples  •  {dur}")

        self._ip_entry.configure(state="normal")
        self._start_btn.configure(text="▶ Start Monitor", fg_color=SAS_BLUE,
                                   hover_color=SAS_BLUE_DARK)
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
        if ok:
            self._status_label.configure(text=f"✅ CSV exported: {os.path.basename(filepath)}",
                                          text_color=STATUS_GOOD)
        else:
            self._status_label.configure(text=f"❌ Export failed: {msg}",
                                          text_color=STATUS_ERROR)

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
                # Save chart as image for PDF embedding
                chart_img_path = None
                try:
                    chart_img_path = os.path.join(
                        os.path.expanduser("~"), ".sas-netdiag", "_multi_chart.png")
                    os.makedirs(os.path.dirname(chart_img_path), exist_ok=True)
                    # Use the canvas postscript export → convert to PNG
                    # This works with pure tkinter, no matplotlib needed
                    self._chart_canvas.update_idletasks()
                    ps_path = chart_img_path.replace(".png", ".eps")
                    self._chart_canvas.postscript(file=ps_path, colormode="color")
                    # Try to convert to PNG via Pillow
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
