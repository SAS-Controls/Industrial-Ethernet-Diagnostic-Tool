"""
SAS Network Diagnostic Tool — Port Scanner View
Scan specific ports on a target device with service identification.
"""

import logging
import threading
import tkinter as tk
from typing import Optional, List

import customtkinter as ctk

from core.port_scanner import (
    PortScannerEngine, PortResult, ScanResult,
    PRESET_COMMON, PRESET_ALLEN_BRADLEY, PRESET_SIEMENS, PRESET_MODBUS,
    PRESET_WEB, SERVICE_MAP,
)
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)


class PortScannerView(ctk.CTkFrame):
    """Port Scanner — test specific ports on a target device."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._engine = PortScannerEngine()
        self._engine.on_port_result = self._on_port_result
        self._engine.on_progress = self._on_progress
        self._engine.on_complete = self._on_complete
        self._results: List[PortResult] = []
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=24, pady=(16, 8))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🔎  Port Scanner",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         side="left", fill="x", expand=True)

        # ── Config Row 1: Target ──────────────────────────────────────────────
        config = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS)
        config.pack(fill="x", padx=24, pady=(0, 4))

        row1 = ctk.CTkFrame(config, fg_color="transparent")
        row1.pack(fill="x", padx=CARD_PADDING, pady=(10, 4))

        ctk.CTkLabel(row1, text="Target IP:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._target_entry = ctk.CTkEntry(
            row1, width=200, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="192.168.1.1",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        self._target_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row1, text="Timeout (ms):", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._timeout_entry = ctk.CTkEntry(
            row1, width=80, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        self._timeout_entry.pack(side="left", padx=(0, 16))
        self._timeout_entry.insert(0, "1000")

        # Scan button
        self._scan_btn = ctk.CTkButton(
            row1, text="Scan Ports", width=120, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            command=self._start_scan,
        )
        self._scan_btn.pack(side="left", padx=(0, 8))

        self._cancel_btn = ctk.CTkButton(
            row1, text="Cancel", width=80, height=INPUT_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color=STATUS_ERROR, hover_color="#DC2626",
            command=self._cancel_scan, state="disabled",
        )
        self._cancel_btn.pack(side="left")

        # ── Config Row 2: Ports ───────────────────────────────────────────────
        row2 = ctk.CTkFrame(config, fg_color="transparent")
        row2.pack(fill="x", padx=CARD_PADDING, pady=(0, 4))

        ctk.CTkLabel(row2, text="Ports:", font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._ports_entry = ctk.CTkEntry(
            row2, height=INPUT_HEIGHT,
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            placeholder_text="80, 443, 502, 44818  or  1-1024",
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
        )
        self._ports_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # ── Preset Buttons ────────────────────────────────────────────────────
        row3 = ctk.CTkFrame(config, fg_color="transparent")
        row3.pack(fill="x", padx=CARD_PADDING, pady=(0, 10))

        ctk.CTkLabel(row3, text="Presets:", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))

        presets = [
            ("Common Industrial", PRESET_COMMON),
            ("Allen-Bradley", PRESET_ALLEN_BRADLEY),
            ("Siemens", PRESET_SIEMENS),
            ("Modbus", PRESET_MODBUS),
            ("Web Services", PRESET_WEB),
        ]
        for name, ports in presets:
            ctk.CTkButton(
                row3, text=name, height=28,
                font=(FONT_FAMILY, FONT_SIZE_TINY),
                fg_color=BG_CARD_HOVER, hover_color=BORDER_COLOR,
                text_color=TEXT_SECONDARY, corner_radius=4,
                command=lambda p=ports: self._set_preset(p),
            ).pack(side="left", padx=(0, 4))

        # ── Progress Bar ─────────────────────────────────────────────────────
        self._progress_frame = ctk.CTkFrame(self, fg_color=BG_CARD,
                                            corner_radius=CARD_CORNER_RADIUS)
        self._progress_frame.pack(fill="x", padx=24, pady=(0, 4))

        prog_inner = ctk.CTkFrame(self._progress_frame, fg_color="transparent")
        prog_inner.pack(fill="x", padx=CARD_PADDING, pady=8)

        self._progress_bar = ctk.CTkProgressBar(
            prog_inner, fg_color=BG_INPUT,
            progress_color=SAS_BLUE, height=12,
        )
        self._progress_bar.pack(fill="x", side="left", expand=True, padx=(0, 12))
        self._progress_bar.set(0)

        self._progress_label = ctk.CTkLabel(
            prog_inner, text="Ready",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED, width=120,
        )
        self._progress_label.pack(side="right")

        # ── Results Area ──────────────────────────────────────────────────────
        results_frame = ctk.CTkFrame(self, fg_color=BG_CARD,
                                     corner_radius=CARD_CORNER_RADIUS)
        results_frame.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        # Results header with stats
        res_header = ctk.CTkFrame(results_frame, fg_color="transparent")
        res_header.pack(fill="x", padx=CARD_PADDING, pady=(10, 4))

        ctk.CTkLabel(res_header, text="Results",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        self._stats_label = ctk.CTkLabel(
            res_header, text="",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED)
        self._stats_label.pack(side="right")

        # Column headers
        col_frame = ctk.CTkFrame(results_frame, fg_color=BG_DARK,
                                  corner_radius=4, height=30)
        col_frame.pack(fill="x", padx=CARD_PADDING, pady=(0, 2))
        col_frame.pack_propagate(False)

        cols = [("Port", 80), ("Status", 90), ("Service", 200),
                ("Response", 100), ("Banner", 300)]
        for text, width in cols:
            ctk.CTkLabel(col_frame, text=text, width=width,
                         font=(FONT_FAMILY, FONT_SIZE_TINY, "bold"),
                         text_color=TEXT_MUTED, anchor="w").pack(
                             side="left", padx=(8, 0))

        # Scrollable results
        self._results_scroll = ctk.CTkScrollableFrame(
            results_frame, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._results_scroll.pack(fill="both", expand=True,
                                   padx=CARD_PADDING, pady=(0, CARD_PADDING))
        enable_touch_scroll(self._results_scroll)

    def _set_preset(self, ports: List[int]):
        self._ports_entry.delete(0, "end")
        self._ports_entry.insert(0, ", ".join(str(p) for p in ports))

    def _start_scan(self):
        target = self._target_entry.get().strip()
        if not target:
            return

        port_text = self._ports_entry.get().strip()
        if not port_text:
            port_text = ", ".join(str(p) for p in PRESET_COMMON)
            self._ports_entry.insert(0, port_text)

        ports = PortScannerEngine.parse_port_input(port_text)
        if not ports:
            return

        try:
            timeout_ms = int(self._timeout_entry.get().strip())
            timeout = timeout_ms / 1000.0
        except ValueError:
            timeout = 1.0

        # Clear previous results
        for widget in self._results_scroll.winfo_children():
            widget.destroy()
        self._results.clear()

        self._scan_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress_bar.set(0)
        self._progress_label.configure(text=f"Scanning 0/{len(ports)}...")
        self._stats_label.configure(text="")

        self._engine.scan(target, ports, timeout=timeout, grab_banner=True)

    def _cancel_scan(self):
        self._engine.cancel()
        self._cancel_btn.configure(state="disabled")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_port_result(self, result: PortResult):
        self.after(0, lambda r=result: self._add_result_row(r))

    def _on_progress(self, scanned: int, total: int):
        self.after(0, lambda: self._update_progress(scanned, total))

    def _on_complete(self, result: ScanResult):
        self.after(0, lambda: self._scan_complete(result))

    # ── UI Updates ────────────────────────────────────────────────────────────

    def _add_result_row(self, result: PortResult):
        # Only show open and filtered (skip closed for cleaner display)
        # Actually show all for completeness
        row_color = BG_CARD_HOVER if len(self._results) % 2 == 0 else "transparent"
        row = ctk.CTkFrame(self._results_scroll, fg_color=row_color,
                          corner_radius=2, height=28)
        row.pack(fill="x", pady=(0, 1))
        row.pack_propagate(False)

        # Port
        ctk.CTkLabel(row, text=str(result.port), width=80,
                     font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                     text_color=TEXT_PRIMARY, anchor="w").pack(
                         side="left", padx=(8, 0))

        # Status with color
        status_colors = {
            "open": STATUS_GOOD,
            "closed": STATUS_ERROR,
            "filtered": STATUS_WARN,
        }
        ctk.CTkLabel(row, text=result.status.upper(), width=90,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                     text_color=status_colors.get(result.status, TEXT_MUTED),
                     anchor="w").pack(side="left", padx=(8, 0))

        # Service
        ctk.CTkLabel(row, text=result.service, width=200,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_SECONDARY, anchor="w").pack(
                         side="left", padx=(8, 0))

        # Response time
        rt_text = f"{result.response_ms:.0f} ms" if result.response_ms else "—"
        ctk.CTkLabel(row, text=rt_text, width=100,
                     font=(FONT_FAMILY_MONO, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED, anchor="w").pack(
                         side="left", padx=(8, 0))

        # Banner
        banner = result.banner[:60] + "..." if len(result.banner) > 60 else result.banner
        ctk.CTkLabel(row, text=banner, width=300,
                     font=(FONT_FAMILY, FONT_SIZE_TINY),
                     text_color=TEXT_MUTED, anchor="w").pack(
                         side="left", padx=(8, 0))

        self._results.append(result)

    def _update_progress(self, scanned: int, total: int):
        progress = scanned / total if total > 0 else 0
        self._progress_bar.set(progress)
        self._progress_label.configure(text=f"Scanning {scanned}/{total}...")

    def _scan_complete(self, result: ScanResult):
        self._scan_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._progress_bar.set(1.0)

        open_count = len(result.open_ports)
        closed_count = len(result.closed_ports)
        filtered_count = len(result.filtered_ports)
        duration = result.duration_seconds

        self._progress_label.configure(
            text=f"Done in {duration:.1f}s")
        self._stats_label.configure(
            text=f"{open_count} open  •  {closed_count} closed  •  "
                 f"{filtered_count} filtered  •  {result.ports_scanned} scanned")

        if result.error:
            self._progress_label.configure(text=f"Error: {result.error}")

    def on_show(self):
        pass
