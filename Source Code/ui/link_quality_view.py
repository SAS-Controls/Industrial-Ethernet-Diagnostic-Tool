"""
SAS Network Diagnostic Tool — Link Quality Analyzer View

Tests an IP address with progressive payload sizes and a burst test to detect:
  - MTU / fragmentation issues
  - Duplex mismatch (latency spikes under burst load)
  - Marginal cable / connector (loss at specific frame sizes)
  - Baseline latency problems
"""

import math
import threading
import tkinter as tk
from datetime import datetime
from typing import List, Optional

import customtkinter as ctk

from core.link_quality import (
    LinkQualityEngine, LQAnalysis, LinkSizeResult, BurstResult, LQFinding,
    PAYLOAD_SIZES, BURST_COUNT, BURST_SIZE,
)
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = __import__("logging").getLogger(__name__)


def _rc(c):
    """Resolve (light, dark) color tuple to dark-mode value for tk.Canvas."""
    return c[1] if isinstance(c, (list, tuple)) else c


CHART_H = 200
CHART_L = 52
CHART_R = 16
CHART_T = 14
CHART_B = 32
BAR_COLORS = {
    "ok":      "#22C55E",
    "warning": "#F59E0B",
    "critical": "#EF4444",
}


class LinkQualityView(ctk.CTkFrame):
    """Link Quality Analyzer — MTU path test, jitter under load, duplex detection."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._engine: Optional[LinkQualityEngine] = None
        self._running = False
        self._size_results: List[LinkSizeResult] = []
        self._analysis: Optional[LQAnalysis] = None
        self._build_ui()

    def on_show(self):
        pass

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 0))

        ctk.CTkLabel(header, text="🔬  Link Quality Analyzer",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        ctk.CTkLabel(header,
                     text="Tests a device with increasing frame sizes to detect MTU issues, "
                          "half-duplex mismatches, and marginal cables.",
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED, anchor="w").pack(side="left", padx=(14, 0))

        # ── Config Card ──────────────────────────────────────────────────────
        cfg = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
                           border_width=1, border_color=BORDER_COLOR)
        cfg.pack(fill="x", padx=20, pady=(12, 0))

        row = ctk.CTkFrame(cfg, fg_color="transparent")
        row.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)

        ctk.CTkLabel(row, text="Target IP:",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._ip_entry = ctk.CTkEntry(
            row, placeholder_text="e.g. 192.168.1.10",
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
            width=200, height=BUTTON_HEIGHT,
        )
        self._ip_entry.pack(side="left", padx=(0, 16))

        self._run_btn = ctk.CTkButton(
            row, text="▶ Run Test",
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            text_color="white", width=120, height=BUTTON_HEIGHT,
            command=self._toggle_test,
        )
        self._run_btn.pack(side="left", padx=(0, 8))

        self._reset_btn = ctk.CTkButton(
            row, text="🔄 New Scan",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=BG_CARD_HOVER, width=110, height=BUTTON_HEIGHT,
            command=self._reset_scan, state="disabled",
        )
        self._reset_btn.pack(side="left", padx=(0, 12))

        self._report_btn = ctk.CTkButton(
            row, text="📄 Export Report",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=SAS_BLUE, text_color=SAS_BLUE_LIGHT,
            hover_color=BG_CARD_HOVER, width=130, height=BUTTON_HEIGHT,
            command=self._export_report, state="disabled",
        )
        self._report_btn.pack(side="left", padx=(0, 12))

        self._status_lbl = ctk.CTkLabel(
            row, text="Enter a target IP and run the test.",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._status_lbl.pack(side="left")

        # Progress bar
        self._progress = ctk.CTkProgressBar(
            cfg, fg_color=BG_MEDIUM, progress_color=SAS_BLUE, height=4,
        )
        self._progress.set(0)
        self._progress.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

        # ── Results scroll area ──────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._scroll.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        enable_touch_scroll(self._scroll)

        self._build_chart_card()
        self._build_burst_card()
        self._results_container = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._results_container.pack(fill="x")

        self._draw_empty_chart()

    def _build_chart_card(self):
        card = ctk.CTkFrame(self._scroll, fg_color=BG_CARD,
                            corner_radius=CARD_CORNER_RADIUS,
                            border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="x", pady=(0, 10))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))

        ctk.CTkLabel(hdr, text="Response Time vs. Payload Size",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(hdr,
                     text="Each bar = avg ping RTT at that payload size.  "
                          "Red = packet loss.  Loss before 1472B = MTU problem.",
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(side="left", padx=(12, 0))

        self._chart_canvas = tk.Canvas(
            card, height=CHART_H, bg=_rc(BG_DARK), highlightthickness=0, bd=0,
        )
        self._chart_canvas.pack(fill="x", padx=8, pady=(4, 8))
        self._chart_canvas.bind("<Configure>", lambda e: self._draw_chart())

    def _build_burst_card(self):
        self._burst_card = ctk.CTkFrame(
            self._scroll, fg_color=BG_CARD,
            corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        self._burst_card.pack(fill="x", pady=(0, 10))

        hdr = ctk.CTkFrame(self._burst_card, fg_color="transparent")
        hdr.pack(fill="x", padx=CARD_PADDING, pady=(CARD_PADDING, 4))

        ctk.CTkLabel(hdr, text=f"Burst Load Test  ({BURST_COUNT} rapid pings @ {BURST_SIZE}B)",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(hdr,
                     text="High jitter under burst = likely duplex mismatch or congested link.",
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=TEXT_MUTED).pack(side="left", padx=(12, 0))

        self._burst_body = ctk.CTkFrame(self._burst_card, fg_color="transparent")
        self._burst_body.pack(fill="x", padx=CARD_PADDING, pady=(0, CARD_PADDING))

        ctk.CTkLabel(self._burst_body, text="Waiting for test to complete…",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_MUTED).pack(pady=8)

    # ── Test control ─────────────────────────────────────────────────────────

    def _toggle_test(self):
        if self._running:
            self._cancel_test()
        else:
            self._start_test()

    def _start_test(self):
        ip = self._ip_entry.get().strip()
        if not ip:
            self._status_lbl.configure(text="⚠ Enter a target IP address.",
                                        text_color=STATUS_WARN)
            return

        self._size_results.clear()
        self._analysis = None

        for w in self._results_container.winfo_children():
            w.destroy()
        self._clear_burst_body()

        self._running = True
        self._run_btn.configure(text="■ Stop", fg_color=STATUS_ERROR,
                                 hover_color="#b91c1c")
        self._ip_entry.configure(state="disabled")
        self._progress.set(0)
        self._draw_empty_chart()

        self._engine = LinkQualityEngine()
        self._engine.start(
            target_ip=ip,
            on_progress=lambda msg, pct: self.after(0, lambda m=msg, p=pct: self._on_progress(m, p)),
            on_size_result=lambda r: self.after(0, lambda rr=r: self._on_size_result(rr)),
            on_complete=lambda a: self.after(0, lambda aa=a: self._on_complete(aa)),
        )

    def _cancel_test(self):
        if self._engine:
            self._engine.cancel()
        self._running = False
        self._run_btn.configure(text="▶ Run Test", fg_color=SAS_BLUE,
                                 hover_color=SAS_BLUE_DARK)
        self._ip_entry.configure(state="normal")
        self._status_lbl.configure(text="Test cancelled.", text_color=TEXT_MUTED)

    def _reset_scan(self):
        """Clear all results and prepare for a fresh scan."""
        if self._running:
            self._cancel_test()
        self._size_results.clear()
        self._analysis = None
        for w in self._results_container.winfo_children():
            w.destroy()
        self._clear_burst_body()
        self._draw_empty_chart()
        self._progress.set(0)
        self._ip_entry.configure(state="normal")
        self._run_btn.configure(text="▶ Run Test", fg_color=SAS_BLUE,
                                 hover_color=SAS_BLUE_DARK, state="normal")
        self._reset_btn.configure(state="disabled")
        self._report_btn.configure(state="disabled")
        self._status_lbl.configure(text="Enter a target IP and run the test.",
                                    text_color=TEXT_MUTED)

    def _export_report(self):
        """Export the link quality analysis as a branded PDF report."""
        if not self._analysis:
            return
        from tkinter import filedialog
        import threading
        timestamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d_%H%M%S")
        ip_safe = self._ip_entry.get().strip().replace(".", "_")
        output_path = filedialog.asksaveasfilename(
            title="Save Link Quality Report",
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
            initialfile=f"LinkQuality_{ip_safe}_{timestamp}.pdf",
            initialdir=__import__("os").path.join(
                __import__("os").path.expanduser("~"), "Documents"),
        )
        if not output_path:
            return
        self._report_btn.configure(text="⏳ Generating…", state="disabled")
        analysis_snap = self._analysis
        sizes_snap = list(self._size_results)

        def _gen():
            try:
                from core.pdf_report import generate_link_quality_report
                generate_link_quality_report(
                    target_ip=self._ip_entry.get().strip(),
                    analysis=analysis_snap,
                    size_results=sizes_snap,
                    output_path=output_path,
                )
                self.after(0, lambda: self._report_btn.configure(
                    text="✅ Saved", state="normal"))
                self.after(3000, lambda: self._report_btn.configure(
                    text="📄 Export Report"))
                try:
                    import platform, subprocess, os
                    if platform.system() == "Windows":
                        os.startfile(output_path)
                    elif platform.system() == "Darwin":
                        subprocess.Popen(["open", output_path])
                    else:
                        subprocess.Popen(["xdg-open", output_path])
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Link quality report failed: {e}", exc_info=True)
                self.after(0, lambda: self._report_btn.configure(
                    text="❌ Export failed", state="normal"))
                self.after(3000, lambda: self._report_btn.configure(
                    text="📄 Export Report"))

        threading.Thread(target=_gen, daemon=True).start()

    def _on_progress(self, message: str, pct: float):
        self._progress.set(pct)
        self._status_lbl.configure(text=message, text_color=TEXT_SECONDARY)

    def _on_size_result(self, result: LinkSizeResult):
        self._size_results.append(result)
        self._draw_chart()

    def _on_complete(self, analysis: LQAnalysis):
        self._analysis = analysis
        self._running = False
        self._run_btn.configure(text="▶ Run Test", fg_color=SAS_BLUE,
                                 hover_color=SAS_BLUE_DARK)
        self._ip_entry.configure(state="normal")
        self._progress.set(1.0)
        self._reset_btn.configure(state="normal")

        if analysis.error:
            self._status_lbl.configure(
                text=f"❌ Error: {analysis.error}", text_color=STATUS_ERROR)
            return

        score = analysis.health_score
        color = STATUS_GOOD if score >= 80 else (STATUS_WARN if score >= 60 else STATUS_ERROR)
        self._status_lbl.configure(
            text=f"Complete — Health Score: {score}/100",
            text_color=color)
        self._report_btn.configure(state="normal")

        self._draw_chart()
        self._build_burst_results(analysis.burst_result)
        self._build_findings(analysis)

    # ── Chart ─────────────────────────────────────────────────────────────────

    def _draw_empty_chart(self):
        c = self._chart_canvas
        c.delete("all")
        w = c.winfo_width() or 800
        mid_y = CHART_H // 2
        c.create_text(w // 2, mid_y,
                       text="Run the test to see results",
                       fill=_rc(TEXT_MUTED), font=(FONT_FAMILY, 11))

    def _draw_chart(self):
        c = self._chart_canvas
        c.delete("all")
        w = c.winfo_width()
        if w < 100:
            w = 800
        h = CHART_H
        if not self._size_results:
            self._draw_empty_chart()
            return

        results   = self._size_results
        n         = len(PAYLOAD_SIZES)
        px0, px1  = CHART_L, w - CHART_R
        py0, py1  = CHART_T, h - CHART_B
        pw        = px1 - px0
        ph        = py1 - py0
        grid_c    = _rc(BORDER_COLOR)
        text_c    = _rc(TEXT_MUTED)

        # Y scale: max RTT across received results
        max_rtt = max((r.avg_ms for r in results if r.ok), default=10.0)
        max_rtt = max(max_rtt * 1.25, 5.0)
        for tick in [2, 5, 10, 20, 50, 100, 200, 500, 1000]:
            if max_rtt <= tick:
                max_rtt = float(tick)
                break

        def val_y(v): return py0 + ph * (1.0 - v / max_rtt)

        # Grid lines
        for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = py0 + ph * frac
            c.create_line(px0, y, px1, y, fill=grid_c, dash=(2, 4))
            val = max_rtt * (1.0 - frac)
            lbl = f"{val:.0f}" if val >= 10 else f"{val:.1f}"
            c.create_text(px0 - 4, y, text=lbl, fill=text_c, anchor="e",
                           font=("Consolas", 8))
        c.create_text(px0 - 4, py0 - 10, text="ms", fill=text_c, anchor="e",
                       font=("Consolas", 8))

        # Bars
        slot_w = pw / n
        bar_w  = max(8, slot_w * 0.55)

        for i, size in enumerate(PAYLOAD_SIZES[:len(results)]):
            r   = results[i]
            x   = px0 + slot_w * i + slot_w / 2

            # X label
            c.create_text(x, py1 + 12, text=f"{size}B", fill=text_c, anchor="n",
                           font=("Consolas", 8))

            if r.timed_out or not r.ok:
                # Red bar showing "no response"
                bar_h = 20
                y_top = py1 - bar_h
                c.create_rectangle(x - bar_w/2, y_top, x + bar_w/2, py1,
                                    fill=BAR_COLORS["critical"], outline="")
                c.create_text(x, y_top - 8, text="✕", fill=BAR_COLORS["critical"],
                               font=("Consolas", 9, "bold"), anchor="s")
            else:
                # Green/amber bar for RTT
                bar_h_px = max(4.0, ph * (r.avg_ms / max_rtt))
                y_top    = py1 - bar_h_px
                color    = BAR_COLORS["ok"] if r.loss_pct == 0 else BAR_COLORS["warning"]
                c.create_rectangle(x - bar_w/2, y_top, x + bar_w/2, py1,
                                    fill=color, outline="")

                # Jitter cap lines
                if r.jitter_ms > 0:
                    jitter_px = ph * r.jitter_ms / max_rtt
                    y_hi = max(py0, y_top - jitter_px / 2)
                    y_lo = min(py1, y_top + jitter_px / 2)
                    c.create_line(x, y_hi, x, y_lo, fill="white", width=1.5)
                    c.create_line(x - 4, y_hi, x + 4, y_hi, fill="white", width=1)
                    c.create_line(x - 4, y_lo, x + 4, y_lo, fill="white", width=1)

                # RTT label above bar
                lbl = f"{r.avg_ms:.1f}" if r.avg_ms < 100 else f"{r.avg_ms:.0f}"
                c.create_text(x, y_top - 4, text=lbl, fill=color, anchor="s",
                               font=("Consolas", 8, "bold"))

                # Loss % if any
                if r.loss_pct > 0:
                    c.create_text(x, y_top - 16, text=f"{r.loss_pct:.0f}%loss",
                                   fill=BAR_COLORS["warning"], anchor="s",
                                   font=("Consolas", 7))

        # Legend
        for label, color in [("OK", BAR_COLORS["ok"]),
                               ("Loss", BAR_COLORS["warning"]),
                               ("Timeout", BAR_COLORS["critical"])]:
            idx = list(BAR_COLORS.values()).index(color)
            lx  = px1 - 200 + idx * 65
            c.create_rectangle(lx, py0 + 4, lx + 10, py0 + 14, fill=color, outline="")
            c.create_text(lx + 14, py0 + 9, text=label, fill=text_c, anchor="w",
                           font=("Consolas", 8))

    # ── Burst results ─────────────────────────────────────────────────────────

    def _clear_burst_body(self):
        for w in self._burst_body.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._burst_body, text="Waiting for test to complete…",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_MUTED).pack(pady=8)

    def _build_burst_results(self, br):
        for w in self._burst_body.winfo_children():
            w.destroy()
        if br is None or br.received == 0:
            ctk.CTkLabel(self._burst_body, text="No burst data — device unreachable.",
                         font=(FONT_FAMILY, FONT_SIZE_BODY),
                         text_color=STATUS_ERROR).pack(pady=8)
            return

        # Stat row
        stat_row = ctk.CTkFrame(self._burst_body, fg_color="transparent")
        stat_row.pack(fill="x", pady=(4, 0))

        jitter_color = (STATUS_GOOD if br.jitter_ms < 5 else
                        STATUS_WARN if br.jitter_ms < 15 else STATUS_ERROR)

        for label, value, color in [
            ("Avg RTT",    f"{br.avg_ms:.1f} ms",    TEXT_PRIMARY),
            ("Min RTT",    f"{br.min_ms:.1f} ms",    STATUS_GOOD),
            ("Max RTT",    f"{br.max_ms:.1f} ms",    STATUS_WARN if br.max_ms > 20 else TEXT_PRIMARY),
            ("Jitter (σ)", f"{br.jitter_ms:.1f} ms", jitter_color),
            ("Packet Loss",f"{br.loss_pct:.0f}%",    STATUS_ERROR if br.loss_pct > 0 else STATUS_GOOD),
        ]:
            box = ctk.CTkFrame(stat_row, fg_color=_rc(BG_MEDIUM),
                               corner_radius=6, width=110)
            box.pack(side="left", padx=(0, 8))
            box.pack_propagate(False)
            ctk.CTkLabel(box, text=label,
                          font=(FONT_FAMILY, FONT_SIZE_TINY),
                          text_color=TEXT_MUTED).pack(pady=(6, 0))
            ctk.CTkLabel(box, text=value,
                          font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
                          text_color=color).pack(pady=(0, 6))

        # Interpretation
        if br.jitter_ms > 15:
            note = ("⚠ Jitter > 15ms under burst — investigate duplex mismatch or link congestion.\n"
                    "Inspect switch port speed/duplex settings for this device.")
            note_color = STATUS_WARN
        elif br.jitter_ms > 5:
            note = "ℹ Moderate jitter — acceptable for most applications, but worth noting."
            note_color = TEXT_SECONDARY
        else:
            note = "✅ Jitter is very low — link is stable under burst traffic."
            note_color = STATUS_GOOD

        ctk.CTkLabel(self._burst_body, text=note,
                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                     text_color=note_color, anchor="w", wraplength=800).pack(
            fill="x", pady=(8, 0))

    # ── Findings ─────────────────────────────────────────────────────────────

    def _build_findings(self, analysis: LQAnalysis):
        for w in self._results_container.winfo_children():
            w.destroy()

        if not analysis.findings:
            return

        ctk.CTkLabel(self._results_container, text="DIAGNOSTIC FINDINGS",
                     font=(FONT_FAMILY, FONT_SIZE_TINY, "bold"),
                     text_color=TEXT_MUTED, anchor="w").pack(
            fill="x", pady=(8, 6))

        # Health score banner
        score = analysis.health_score
        score_color = (STATUS_GOOD if score >= 80 else
                       STATUS_WARN  if score >= 60 else STATUS_ERROR)
        banner = ctk.CTkFrame(self._results_container, fg_color=BG_CARD,
                               corner_radius=CARD_CORNER_RADIUS,
                               border_width=1, border_color=score_color)
        banner.pack(fill="x", pady=(0, 8))
        brow = ctk.CTkFrame(banner, fg_color="transparent")
        brow.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)
        ctk.CTkLabel(brow, text=f"Link Health Score: {score}/100",
                     font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
                     text_color=score_color).pack(side="left")
        if analysis.mtu_limit:
            ctk.CTkLabel(brow, text=f"  ·  Largest clean payload: {analysis.mtu_limit}B",
                         font=(FONT_FAMILY, FONT_SIZE_BODY),
                         text_color=TEXT_MUTED).pack(side="left")

        # Findings
        sev_border = {"ok": BORDER_COLOR, "warning": "#F59E0B", "critical": "#EF4444"}
        sev_label  = {"ok": STATUS_GOOD,  "warning": STATUS_WARN, "critical": STATUS_ERROR}

        for f in analysis.findings:
            card = ctk.CTkFrame(
                self._results_container, fg_color=BG_CARD,
                corner_radius=CARD_CORNER_RADIUS,
                border_width=1,
                border_color=sev_border.get(f.severity, BORDER_COLOR),
            )
            card.pack(fill="x", pady=(0, 8))

            card_inner = ctk.CTkFrame(card, fg_color="transparent")
            card_inner.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)

            ctk.CTkLabel(card_inner, text=f.title,
                          font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
                          text_color=sev_label.get(f.severity, TEXT_PRIMARY),
                          anchor="w").pack(fill="x")

            ctk.CTkLabel(card_inner, text=f.detail,
                          font=(FONT_FAMILY, FONT_SIZE_SMALL),
                          text_color=TEXT_SECONDARY, anchor="w",
                          justify="left", wraplength=850).pack(
                fill="x", pady=(6, 0))
