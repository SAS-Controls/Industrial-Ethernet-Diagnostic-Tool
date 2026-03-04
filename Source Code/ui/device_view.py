"""
SAS Network Diagnostics Tool — Device Detail View
Displays comprehensive diagnostics for a selected device in plain English.
"""

import logging
import os
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from core.network_utils import DiscoveredDevice, ping_host
from core.eip_scanner import (
    EIPIdentity, EthernetDiagnostics,
    read_cip_diagnostics, read_device_diagnostics_via_http,
)
from core.analyzer import (
    DiagnosticReport, Severity, analyze_diagnostics, continuous_ping_test,
)
from ui.theme import *
from ui.widgets import FindingCard, HealthGauge, InfoCard, StatusBadge, enable_touch_scroll

logger = logging.getLogger(__name__)


class DeviceDetailView(ctk.CTkFrame):
    """Detailed diagnostic view for a single device."""

    def __init__(self, master, on_back: Callable = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_back = on_back
        self._device: Optional[DiscoveredDevice] = None
        self._eip_identity: Optional[EIPIdentity] = None
        self._diagnostics: Optional[EthernetDiagnostics] = None
        self._prev_diagnostics: Optional[EthernetDiagnostics] = None
        self._report: Optional[DiagnosticReport] = None
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

        self._build_ui()

    def _build_ui(self):
        # ── Top Bar ──────────────────────────────────────────────────────────
        topbar = ctk.CTkFrame(self, fg_color="transparent")
        topbar.pack(fill="x", padx=20, pady=(16, 0))

        self._back_btn = ctk.CTkButton(
            topbar, text="← Back to Scan Results",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", text_color=SAS_BLUE_LIGHT,
            hover_color=BG_CARD_HOVER, anchor="w",
            width=200, height=BUTTON_HEIGHT,
            command=self._go_back,
        )
        self._back_btn.pack(side="left")

        # Action buttons
        btn_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        btn_frame.pack(side="right")

        self._export_btn = ctk.CTkButton(
            btn_frame, text="📄 Export Report",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=BG_CARD_HOVER, width=140, height=BUTTON_HEIGHT,
            command=self._export_report, state="disabled",
        )
        self._export_btn.pack(side="left", padx=(0, 8))

        self._diagnose_btn = ctk.CTkButton(
            btn_frame, text="🔍 Run Full Diagnostic",
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            text_color="white", width=180, height=BUTTON_HEIGHT,
            command=self._run_diagnostics,
        )
        self._diagnose_btn.pack(side="left", padx=(0, 8))

        self._monitor_btn = ctk.CTkButton(
            btn_frame, text="📊 Start Monitoring",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=SAS_BLUE, text_color=SAS_BLUE_LIGHT,
            hover_color=BG_CARD_HOVER, width=160, height=BUTTON_HEIGHT,
            command=self._toggle_monitoring,
        )
        self._monitor_btn.pack(side="left")

        # ── Scrollable Content ───────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._scroll.pack(fill="both", expand=True, padx=20, pady=(12, 20))
        enable_touch_scroll(self._scroll)

        # ── Device Header Card ───────────────────────────────────────────────
        self._header_card = ctk.CTkFrame(
            self._scroll, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        self._header_card.pack(fill="x", pady=(0, 12))

        header_inner = ctk.CTkFrame(self._header_card, fg_color="transparent")
        header_inner.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)

        # Left side: device info
        info_left = ctk.CTkFrame(header_inner, fg_color="transparent")
        info_left.pack(side="left", fill="x", expand=True)

        self._device_name_label = ctk.CTkLabel(
            info_left, text="Device Name",
            font=(FONT_FAMILY, FONT_SIZE_HEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        )
        self._device_name_label.pack(fill="x")

        self._device_ip_label = ctk.CTkLabel(
            info_left, text="0.0.0.0",
            font=(FONT_FAMILY_MONO, FONT_SIZE_SUBHEADING),
            text_color=SAS_BLUE_LIGHT, anchor="w",
        )
        self._device_ip_label.pack(fill="x", pady=(2, 8))

        # Device detail grid
        self._detail_grid = ctk.CTkFrame(info_left, fg_color="transparent")
        self._detail_grid.pack(fill="x")

        self._detail_labels = {}
        detail_fields = [
            ("Vendor", "vendor"), ("Product", "product"),
            ("Firmware", "firmware"), ("Serial", "serial"),
            ("Device Type", "dev_type"), ("MAC Address", "mac"),
            ("Status", "status"),
        ]
        for i, (label, key) in enumerate(detail_fields):
            row = i // 2
            col = i % 2
            frame = ctk.CTkFrame(self._detail_grid, fg_color="transparent")
            frame.grid(row=row, column=col, sticky="w", padx=(0, 40), pady=2)
            ctk.CTkLabel(frame, text=f"{label}:", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                         text_color=TEXT_MUTED, width=80, anchor="w").pack(side="left")
            val_label = ctk.CTkLabel(frame, text="—",
                                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                     text_color=TEXT_PRIMARY, anchor="w")
            val_label.pack(side="left")
            self._detail_labels[key] = val_label

        # Right side: health gauge
        self._gauge = HealthGauge(header_inner, size=140)
        self._gauge.pack(side="right", padx=(20, 0))

        # ── Status Message ───────────────────────────────────────────────────
        self._status_card = ctk.CTkFrame(
            self._scroll, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        self._status_card.pack(fill="x", pady=(0, 12))

        self._status_label = ctk.CTkLabel(
            self._status_card, text="Click 'Run Full Diagnostic' to analyze this device.",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_SECONDARY, anchor="w", wraplength=700,
            justify="left",
        )
        self._status_label.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)

        # ── Findings Container ───────────────────────────────────────────────
        self._findings_label = ctk.CTkLabel(
            self._scroll, text="Diagnostic Findings",
            font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        )

        self._findings_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")

    def load_device(self, device: DiscoveredDevice, eip_identity: Optional[EIPIdentity] = None):
        """Load a device and display its information."""
        self._device = device
        self._eip_identity = eip_identity
        self._diagnostics = None
        self._prev_diagnostics = None
        self._report = None

        # Update header
        self._device_name_label.configure(text=device.display_name)
        self._device_ip_label.configure(text=device.ip_address)
        self._gauge.set_score(0)

        # Determine manufacturer from MAC if not already known
        vendor_display = device.vendor or device.device_type or "—"
        if (not device.vendor or device.vendor == "Unknown") and device.mac_address:
            from core.mac_vendors import lookup_vendor, get_category_label
            mac_vendor, mac_cat = lookup_vendor(device.mac_address)
            if mac_vendor != "Unknown":
                vendor_display = mac_vendor
                device.vendor = mac_vendor

        # Update detail fields
        if eip_identity:
            self._detail_labels["vendor"].configure(text=eip_identity.vendor_name)
            self._detail_labels["product"].configure(text=eip_identity.product_name or "—")
            self._detail_labels["firmware"].configure(text=eip_identity.firmware_version)
            self._detail_labels["serial"].configure(text=eip_identity.serial_hex)
            self._detail_labels["dev_type"].configure(text=eip_identity.device_type_name)
            self._detail_labels["status"].configure(text=eip_identity.status_description)
        else:
            self._detail_labels["vendor"].configure(text=vendor_display)
            self._detail_labels["product"].configure(text=device.product_name or "—")
            self._detail_labels["firmware"].configure(text=device.firmware_rev or "—")
            self._detail_labels["serial"].configure(text=device.serial_number or "—")
            self._detail_labels["dev_type"].configure(text=device.device_type or "—")
            self._detail_labels["status"].configure(text="—")

        self._detail_labels["mac"].configure(text=device.mac_address or "—")

        # Reset findings
        self._clear_findings()

        is_eip = eip_identity is not None or 44818 in (device.open_ports or [])
        if is_eip:
            desc = ("Click 'Run Full Diagnostic' to analyze this device's network health.\n\n"
                    "The diagnostic will:\n"
                    "• Run a series of ping tests to check response time and packet loss\n"
                    "• Read Ethernet Link counters (errors, collisions, speed/duplex)\n"
                    "• Read TCP/IP configuration (IP method, ACD conflict detection, multicast)\n"
                    "• Read Connection Manager stats (timeouts, rejected connections)\n"
                    "• Analyze all data and explain any problems in plain English")
        else:
            desc = ("Click 'Run Full Diagnostic' to analyze this device's network health.\n\n"
                    "The diagnostic will:\n"
                    "• Run a series of ping tests to check response time and packet loss\n"
                    "• Attempt to read CIP diagnostic data (Ethernet Link, TCP/IP, Connection Manager)\n"
                    "• Analyze all the data and explain any problems in plain English\n\n"
                    "Note: Devices that don't support CIP or have a web interface will still get "
                    "ping-based diagnostics including latency, jitter, and packet loss analysis.")

        self._status_label.configure(text=desc, text_color=TEXT_SECONDARY)

    def _run_diagnostics(self):
        """Run a full diagnostic on the selected device."""
        if not self._device:
            return

        self._diagnose_btn.configure(text="⏳ Running...", state="disabled")
        self._status_label.configure(text="Running diagnostic tests...", text_color=SAS_BLUE_LIGHT)
        self._clear_findings()

        def run():
            try:
                ip = self._device.ip_address
                self.after(0, lambda: self._status_label.configure(
                    text="Step 1/4: Running ping tests (20 pings)..."))

                # Step 1: Ping test
                avg_ms, loss_pct, times = continuous_ping_test(
                    ip, count=20, interval=0.3,
                    progress_callback=lambda c, t: self.after(0, lambda:
                        self._status_label.configure(
                            text=f"Step 1/4: Ping test ({c}/{t})...")),
                )

                if self._device:
                    self._device.response_time_ms = avg_ms

                # Step 2: Read CIP diagnostics (Ethernet Link, TCP/IP, Connection Manager)
                self.after(0, lambda: self._status_label.configure(
                    text="Step 2/4: Reading CIP diagnostics (Ethernet Link, TCP/IP, Connection Manager)..."))

                self._prev_diagnostics = self._diagnostics
                diag = None

                # Try CIP first (works on EtherNet/IP devices — AB, Turck, WAGO, etc.)
                diag = read_cip_diagnostics(ip, timeout=5.0)

                # Step 3: Fall back to HTTP if CIP didn't return counters
                if not diag or diag.total_packets == 0:
                    self.after(0, lambda: self._status_label.configure(
                        text="Step 3/4: Trying HTTP diagnostics page..."))
                    http_diag = read_device_diagnostics_via_http(ip, timeout=5.0)
                    if http_diag and http_diag.total_packets > 0:
                        diag = http_diag

                if not diag:
                    diag = EthernetDiagnostics()
                    self.after(0, lambda: self._status_label.configure(
                        text="Step 3/4: No CIP/HTTP counters available — using ping data..."))

                self._diagnostics = diag

                # Step 4: Analyze
                self.after(0, lambda: self._status_label.configure(
                    text="Step 4/4: Analyzing diagnostic data..."))

                report = analyze_diagnostics(
                    diag=diag,
                    prev_diag=self._prev_diagnostics,
                    device_ip=ip,
                    device_name=self._device.display_name,
                    ping_ms=avg_ms,
                    packet_loss_pct=loss_pct,
                )
                self._report = report

                # Update UI
                self.after(0, lambda: self._display_report(report))

            except Exception as e:
                logger.error(f"Diagnostic failed: {e}", exc_info=True)
                self.after(0, lambda: self._diagnostic_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _display_report(self, report: DiagnosticReport):
        """Display the diagnostic report in the UI."""
        self._diagnose_btn.configure(text="🔍 Run Full Diagnostic", state="normal")
        self._export_btn.configure(state="normal")

        # Update health gauge
        self._gauge.set_score(report.health_score)

        # Update status message
        status_color = get_health_color(report.health_score)
        self._status_label.configure(
            text=f"Overall Status: {report.overall_status}\n\n{report.overall_summary}",
            text_color=status_color,
        )

        # Display findings
        self._clear_findings()
        self._findings_label.pack(fill="x", pady=(12, 8))
        self._findings_frame.pack(fill="x", pady=(0, 12))

        # Sort: critical first, then warnings, then ok, then info
        severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1,
                          Severity.OK: 2, Severity.INFO: 3}
        sorted_findings = sorted(report.findings,
                                  key=lambda f: severity_order.get(f.severity, 4))

        # Show summary counts
        counts_frame = ctk.CTkFrame(self._findings_frame, fg_color="transparent")
        counts_frame.pack(fill="x", pady=(0, 8))

        if report.critical_count > 0:
            StatusBadge(counts_frame, f"🔴 {report.critical_count} Problems",
                        STATUS_ERROR).pack(side="left", padx=(0, 6))
        if report.warning_count > 0:
            StatusBadge(counts_frame, f"⚠️ {report.warning_count} Warnings",
                        STATUS_WARN).pack(side="left", padx=(0, 6))
        StatusBadge(counts_frame, f"✅ {report.ok_count} OK",
                    STATUS_GOOD).pack(side="left", padx=(0, 6))

        for finding in sorted_findings:
            card = FindingCard(
                self._findings_frame,
                title=finding.title,
                severity=finding.severity.value,
                summary=finding.summary,
                explanation=finding.explanation,
                recommendation=finding.recommendation,
                raw_value=finding.raw_value,
            )
            card.pack(fill="x", pady=(0, 6))

    def _diagnostic_error(self, error: str):
        self._diagnose_btn.configure(text="🔍 Run Full Diagnostic", state="normal")
        self._status_label.configure(
            text=f"Diagnostic encountered an error: {error}\n\n"
                 "The device may not support all diagnostic features. "
                 "Basic ping diagnostics may still work.",
            text_color=STATUS_ERROR,
        )

    def _clear_findings(self):
        self._findings_label.pack_forget()
        self._findings_frame.pack_forget()
        for widget in self._findings_frame.winfo_children():
            widget.destroy()

    def _toggle_monitoring(self):
        """Toggle continuous monitoring mode."""
        if self._monitoring:
            self._monitoring = False
            self._monitor_btn.configure(text="📊 Start Monitoring",
                                         fg_color="transparent",
                                         border_color=SAS_BLUE)
        else:
            self._monitoring = True
            self._monitor_btn.configure(text="⏹ Stop Monitoring",
                                         fg_color=SAS_ORANGE,
                                         border_color=SAS_ORANGE,
                                         text_color="white")
            self._run_monitor_loop()

    def _run_monitor_loop(self):
        """Continuously poll the device and update diagnostics."""
        if not self._monitoring or not self._device:
            return

        def poll():
            if not self._monitoring:
                return

            ip = self._device.ip_address
            reachable, rtt = ping_host(ip, timeout=2.0)

            if reachable:
                self._prev_diagnostics = self._diagnostics
                diag = read_cip_diagnostics(ip, timeout=3.0)
                if diag:
                    self._diagnostics = diag

                report = analyze_diagnostics(
                    diag=self._diagnostics or EthernetDiagnostics(),
                    prev_diag=self._prev_diagnostics,
                    device_ip=ip,
                    device_name=self._device.display_name,
                    ping_ms=rtt,
                    packet_loss_pct=0,
                )
                self.after(0, lambda: self._display_report(report))
            else:
                self.after(0, lambda: self._status_label.configure(
                    text="⚠️ Device is not responding to pings!",
                    text_color=STATUS_ERROR,
                ))

            # Schedule next poll
            if self._monitoring:
                self.after(5000, self._run_monitor_loop)

        threading.Thread(target=poll, daemon=True).start()

    def _export_report(self):
        """Export the diagnostic report to PDF."""
        if not self._report or not self._device:
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=f"Diagnostic_{self._device.ip_address}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.pdf",
        )
        if not filepath:
            return

        self._export_btn.configure(text="⏳ Exporting...", state="disabled")

        def generate():
            try:
                from core.pdf_report import generate_device_diagnostic_report
                result_path = generate_device_diagnostic_report(
                    device=self._device,
                    eip_identity=self._eip_identity,
                    diagnostics=self._diagnostics,
                    report=self._report,
                    output_path=filepath,
                )
                self.after(0, lambda: self._export_done(result_path))
            except Exception as e:
                logger.error(f"Export failed: {e}", exc_info=True)
                self.after(0, lambda: self._export_error(str(e)))

        threading.Thread(target=generate, daemon=True).start()

    def _export_done(self, path: str):
        self._export_btn.configure(text="📄 Export Report", state="normal")
        self._status_label.configure(
            text=f"✅ Report exported: {os.path.basename(path)}",
            text_color=STATUS_GOOD)

    def _export_error(self, error: str):
        self._export_btn.configure(text="📄 Export Report", state="normal")
        self._status_label.configure(
            text=f"❌ Export failed: {error}",
            text_color=STATUS_ERROR)

    def _go_back(self):
        self._monitoring = False
        if self._on_back:
            self._on_back()
