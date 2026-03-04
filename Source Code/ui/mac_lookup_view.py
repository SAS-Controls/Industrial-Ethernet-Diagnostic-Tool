"""
SAS Network Diagnostic Tool — MAC Address Lookup View
Enter one or more MAC addresses to identify the manufacturer.
Checks local database first, then queries the web for unknown OUIs.
"""

import logging
import re
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import List, Tuple

import customtkinter as ctk

from core.mac_vendors import lookup_vendor, MAC_VENDOR_DB
from core.mac_online_lookup import lookup_vendor_online
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)


def resolve_color(c):
    if isinstance(c, (list, tuple)):
        return c[1]
    return c


# Category colors
CATEGORY_COLORS = {
    "automation": "#0070BB",
    "networking": "#22C55E",
    "computing":  "#A855F7",
    "other":      "#6B7280",
}


class MACLookupView(ctk.CTkFrame):
    """MAC address vendor lookup with local + online resolution."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._lookup_results: List[dict] = []
        self._build_ui()

    def on_show(self):
        self._input_box.focus_set()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 0))

        ctk.CTkLabel(header, text="🔎  MAC Address Lookup",
                     font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        self._count_label = ctk.CTkLabel(
            header, text="",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED)
        self._count_label.pack(side="right")

        # ── Input Card ───────────────────────────────────────────────────────
        input_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=CARD_CORNER_RADIUS,
                                   border_width=1, border_color=BORDER_COLOR)
        input_card.pack(fill="x", padx=20, pady=(12, 0))

        input_inner = ctk.CTkFrame(input_card, fg_color="transparent")
        input_inner.pack(fill="x", padx=CARD_PADDING, pady=CARD_PADDING)

        top_row = ctk.CTkFrame(input_inner, fg_color="transparent")
        top_row.pack(fill="x")

        ctk.CTkLabel(top_row, text="MAC Address(es):",
                     font=(FONT_FAMILY, FONT_SIZE_BODY),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 8))

        self._input_box = ctk.CTkEntry(
            top_row,
            placeholder_text="e.g. 00:1D:9C:AB:CD:EF, 00-0A-E4-12-34-56, 001d.9cab.cdef",
            font=(FONT_FAMILY_MONO, FONT_SIZE_BODY),
            fg_color=BG_INPUT, border_color=BORDER_COLOR,
            width=500, height=BUTTON_HEIGHT,
        )
        self._input_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._input_box.bind("<Return>", lambda e: self._run_lookup())

        self._lookup_btn = ctk.CTkButton(
            top_row, text="🔍 Lookup",
            font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
            fg_color=SAS_BLUE, hover_color=SAS_BLUE_DARK,
            text_color="white", width=120, height=BUTTON_HEIGHT,
            command=self._run_lookup,
        )
        self._lookup_btn.pack(side="left", padx=(0, 4))

        self._clear_btn = ctk.CTkButton(
            top_row, text="Clear",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            fg_color="transparent", border_width=1,
            border_color=BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=BG_CARD_HOVER, width=70, height=BUTTON_HEIGHT,
            command=self._clear_results,
        )
        self._clear_btn.pack(side="left")

        # Hint
        hint_text = (
            "Enter one or more MAC addresses separated by commas, spaces, or newlines. "
            "Accepts formats: AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABB.CCDD.EEFF, or raw hex. "
            "If the address is not in the local database, it will be looked up online."
        )
        self._hint_label = ctk.CTkLabel(
            input_inner, text=hint_text,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED, anchor="w", wraplength=800, justify="left",
        )
        self._hint_label.pack(fill="x", pady=(6, 0))

        # Status
        self._status_label = ctk.CTkLabel(
            input_inner, text="",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._status_label.pack(fill="x", pady=(4, 0))

        # ── Results ──────────────────────────────────────────────────────────
        self._results_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=SAS_BLUE,
        )
        self._results_scroll.pack(fill="both", expand=True, padx=20, pady=(8, 20))
        enable_touch_scroll(self._results_scroll)

        # Placeholder
        self._placeholder = ctk.CTkLabel(
            self._results_scroll,
            text="Enter MAC addresses above and click Lookup\n\n"
                 f"Local database contains {len(MAC_VENDOR_DB)} OUI entries\n"
                 "covering industrial automation, networking, and computing vendors.\n"
                 "Unknown addresses will be searched online via the IEEE OUI registry.",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_MUTED, justify="center",
        )
        self._placeholder.pack(pady=60)

    # ── Lookup Logic ─────────────────────────────────────────────────────────

    def _parse_macs(self, raw: str) -> List[str]:
        """Parse and normalize MAC addresses from raw input."""
        # Replace common separators
        cleaned = raw.replace(",", " ").replace(";", " ").replace("\n", " ")

        macs = []
        for token in cleaned.split():
            token = token.strip()
            if not token:
                continue

            # Strip any non-hex characters to normalize
            hex_only = re.sub(r"[^0-9A-Fa-f]", "", token)

            if len(hex_only) < 6:
                continue  # Need at least OUI (3 bytes)

            if len(hex_only) > 12:
                hex_only = hex_only[:12]  # Truncate extra

            # Format as XX:XX:XX:XX:XX:XX
            upper = hex_only.upper()
            if len(upper) >= 12:
                mac = ":".join(upper[i:i+2] for i in range(0, 12, 2))
            elif len(upper) >= 6:
                # Partial MAC — pad with zeros for display but use OUI for lookup
                padded = upper.ljust(12, "0")
                mac = ":".join(padded[i:i+2] for i in range(0, 12, 2))
            else:
                continue

            macs.append(mac)

        return macs

    def _run_lookup(self):
        """Run MAC address lookup."""
        raw = self._input_box.get().strip()
        if not raw:
            self._status_label.configure(text="⚠ Enter at least one MAC address",
                                          text_color=STATUS_WARN)
            return

        macs = self._parse_macs(raw)
        if not macs:
            self._status_label.configure(text="⚠ No valid MAC addresses found",
                                          text_color=STATUS_WARN)
            return

        self._status_label.configure(
            text=f"Looking up {len(macs)} address(es)...",
            text_color=SAS_BLUE_LIGHT)
        self._lookup_btn.configure(state="disabled", text="⏳ Looking up...")

        def do_lookup():
            results = []
            for i, mac in enumerate(macs):
                oui = mac[:8]  # "XX:XX:XX"
                vendor, category = lookup_vendor(mac)
                source = "local"

                if not vendor or vendor in ("Unknown", ""):
                    # Try online lookup
                    self.after(0, lambda m=mac, idx=i: self._status_label.configure(
                        text=f"Looking up {idx + 1}/{len(macs)}: {m} (searching online...)",
                        text_color=SAS_BLUE_LIGHT))
                    online_vendor, online_category = lookup_vendor_online(mac)
                    if online_vendor and online_vendor not in ("Unknown", ""):
                        vendor = online_vendor
                        category = online_category
                        source = "online"
                    else:
                        source = "not found"

                results.append({
                    "mac": mac,
                    "oui": oui,
                    "vendor": vendor if vendor else "Unknown",
                    "category": category if category else "other",
                    "source": source,
                })

            self._lookup_results.extend(results)
            self.after(0, lambda: self._display_results(results))

        threading.Thread(target=do_lookup, daemon=True).start()

    def _display_results(self, results: List[dict]):
        """Display lookup results as cards."""
        self._lookup_btn.configure(state="normal", text="🔍 Lookup")
        self._placeholder.pack_forget()

        found = sum(1 for r in results if r["source"] != "not found")
        self._status_label.configure(
            text=f"✅ Resolved {found}/{len(results)} addresses",
            text_color=STATUS_GOOD if found == len(results) else STATUS_WARN)
        self._count_label.configure(
            text=f"{len(self._lookup_results)} total lookups")

        for r in results:
            self._add_result_card(r)

    def _add_result_card(self, result: dict):
        """Add a result card to the results area."""
        cat_color = CATEGORY_COLORS.get(result["category"], "#6B7280")

        card = ctk.CTkFrame(
            self._results_scroll, fg_color=BG_CARD,
            corner_radius=CARD_CORNER_RADIUS,
            border_width=1, border_color=BORDER_COLOR,
        )
        card.pack(fill="x", pady=(0, 6))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=CARD_PADDING, pady=(10, 10))

        # Left: MAC + OUI
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        mac_label = ctk.CTkLabel(
            left, text=result["mac"],
            font=(FONT_FAMILY_MONO, FONT_SIZE_SUBHEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        )
        mac_label.pack(fill="x")

        # Vendor name
        vendor_text = result["vendor"]
        if result["source"] == "not found":
            vendor_text = "Unknown Vendor"
        vendor_label = ctk.CTkLabel(
            left, text=vendor_text,
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=cat_color, anchor="w",
        )
        vendor_label.pack(fill="x", pady=(2, 0))

        # OUI + source
        detail = f"OUI: {result['oui']}"
        if result["source"] == "online":
            detail += "  •  Resolved via IEEE online lookup"
        elif result["source"] == "local":
            detail += "  •  Found in local database"
        else:
            detail += "  •  Not found in local or online databases"

        ctk.CTkLabel(
            left, text=detail,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Right: category badge
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right", padx=(16, 0))

        cat_text = result["category"].title()
        badge = ctk.CTkLabel(
            right, text=cat_text,
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
            text_color="white", fg_color=cat_color,
            corner_radius=4, width=90, height=24,
        )
        badge.pack()

        # Source indicator
        if result["source"] == "not found":
            src_color = STATUS_ERROR
            src_icon = "❌"
        elif result["source"] == "online":
            src_color = SAS_BLUE_LIGHT
            src_icon = "🌐"
        else:
            src_color = STATUS_GOOD
            src_icon = "📁"

        ctk.CTkLabel(
            right, text=f"{src_icon} {result['source']}",
            font=(FONT_FAMILY, FONT_SIZE_TINY),
            text_color=src_color,
        ).pack(pady=(4, 0))

    def _clear_results(self):
        """Clear all results."""
        self._lookup_results = []
        for w in self._results_scroll.winfo_children():
            w.destroy()

        self._placeholder = ctk.CTkLabel(
            self._results_scroll,
            text="Enter MAC addresses above and click Lookup\n\n"
                 f"Local database contains {len(MAC_VENDOR_DB)} OUI entries",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_MUTED, justify="center",
        )
        self._placeholder.pack(pady=60)

        self._status_label.configure(text="", text_color=TEXT_MUTED)
        self._count_label.configure(text="")
        self._input_box.delete(0, "end")
