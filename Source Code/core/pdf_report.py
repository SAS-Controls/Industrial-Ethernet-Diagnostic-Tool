"""
SAS Network Diagnostics Tool — PDF Report Generator
Creates professional branded network scan reports using ReportLab.

Uses SAS branding (logo, colors, typography) to produce a polished
PDF document listing all discovered devices with their details.
"""

import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── SAS Brand Constants (mirrored from theme.py) ─────────────────────────────
SAS_BLUE_HEX = "#0070BB"
SAS_ORANGE_HEX = "#E8722A"
SAS_BLUE_DARK_HEX = "#005A96"
HEADER_BG_HEX = "#0070BB"
ROW_ALT_HEX = "#F0F5FA"
ROW_WHITE_HEX = "#FFFFFF"
BORDER_HEX = "#CCCCCC"
TEXT_DARK_HEX = "#1A1A2E"
TEXT_SECONDARY_HEX = "#4A5568"


def _hex_to_color(hex_str: str):
    """Convert hex color string to ReportLab Color object."""
    from reportlab.lib.colors import HexColor
    return HexColor(hex_str)


def _get_logo_path() -> str:
    """Find the SAS logo for PDF reports."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Preferred: logo_pdf.jpg (white background, no alpha — safe for ReportLab)
    candidates = [
        os.path.join(base, "assets", "logo_pdf.jpg"),
        os.path.join(base, "assets", "logo_pdf.png"),
        os.path.join(base, "assets", "logo_light.png"),
        os.path.join(base, "assets", "logo.png"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def generate_scan_report(
    devices: list,
    eip_identities: Optional[Dict] = None,
    interface_name: str = "",
    interface_ip: str = "",
    scan_time: str = "",
    output_path: str = "",
) -> str:
    """
    Generate a branded PDF network scan report.

    Args:
        devices: List of DiscoveredDevice objects
        eip_identities: Dict mapping IP → EIPIdentity (optional)
        interface_name: Name of the scanned network adapter
        interface_ip: IP address of the scanning adapter
        scan_time: Human-readable scan duration string
        output_path: Where to save the PDF (auto-generated if empty)

    Returns:
        Path to the generated PDF file
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, KeepTogether,
    )
    from reportlab.lib.colors import HexColor, white, black, lightgrey

    eip_identities = eip_identities or {}

    # ── Output path ───────────────────────────────────────────────────────
    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, f"Network_Scan_{timestamp}.pdf")

    # ── Colors ────────────────────────────────────────────────────────────
    sas_blue = HexColor(SAS_BLUE_HEX)
    sas_orange = HexColor(SAS_ORANGE_HEX)
    sas_blue_dark = HexColor(SAS_BLUE_DARK_HEX)
    header_bg = HexColor(HEADER_BG_HEX)
    row_alt = HexColor(ROW_ALT_HEX)
    text_dark = HexColor(TEXT_DARK_HEX)
    text_secondary = HexColor(TEXT_SECONDARY_HEX)
    border_color = HexColor(BORDER_HEX)

    # ── Page setup ────────────────────────────────────────────────────────
    page_w, page_h = landscape(letter)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(letter),
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.6 * inch,
    )

    # ── Styles ────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "SASTitle", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=18,
        textColor=sas_blue, spaceAfter=4,
    )
    style_subtitle = ParagraphStyle(
        "SASSubtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10,
        textColor=text_secondary, spaceAfter=2,
    )
    style_heading = ParagraphStyle(
        "SASHeading", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=12,
        textColor=sas_blue, spaceBefore=12, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "SASBody", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9,
        textColor=text_dark,
    )
    style_small = ParagraphStyle(
        "SASSmall", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=text_secondary,
    )
    style_cell = ParagraphStyle(
        "SASCell", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=text_dark, leading=10,
    )
    style_cell_bold = ParagraphStyle(
        "SASCellBold", parent=style_cell,
        fontName="Helvetica-Bold",
    )
    style_header_cell = ParagraphStyle(
        "SASHeaderCell", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=8,
        textColor=white, leading=10,
    )
    style_footer = ParagraphStyle(
        "SASFooter", parent=styles["Normal"],
        fontName="Helvetica", fontSize=7,
        textColor=text_secondary, alignment=TA_CENTER,
    )
    style_company = ParagraphStyle(
        "SASCompany", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=14,
        textColor=sas_blue, spaceAfter=2,
    )
    style_company_info = ParagraphStyle(
        "SASCompanyInfo", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=text_secondary, leading=11,
    )

    story = []

    # ── Header: Logo + Company Info ───────────────────────────────────────
    logo_path = _get_logo_path()

    header_data = []
    if logo_path:
        try:
            logo_img = Image(logo_path, width=1.3 * inch, height=1.08 * inch)
            logo_img.hAlign = "LEFT"
        except Exception:
            logo_img = Paragraph("SAS", style_company)
    else:
        logo_img = Paragraph("SAS", style_company)

    company_text = (
        '<font name="Helvetica-Bold" size="14" color="{blue}">Southern Automation Solutions</font><br/>'
        '<font name="Helvetica" size="8" color="{gray}">111 Hemlock St. Ste A, Valdosta, GA 31601</font><br/>'
        '<font name="Helvetica" size="8" color="{gray}">Contact@SASControls.com  |  229-563-2897</font>'
    ).format(blue=SAS_BLUE_HEX, gray=TEXT_SECONDARY_HEX)
    company_para = Paragraph(company_text, style_body)

    now = datetime.now()
    date_text = (
        '<font name="Helvetica" size="8" color="{gray}">'
        '{date}<br/>{time}</font>'
    ).format(
        gray=TEXT_SECONDARY_HEX,
        date=now.strftime("%B %d, %Y"),
        time=now.strftime("%I:%M %p"),
    )
    date_para = Paragraph(date_text, ParagraphStyle(
        "DateRight", parent=style_body, alignment=TA_RIGHT,
    ))

    avail_w = page_w - 1.0 * inch  # total usable width
    header_table = Table(
        [[logo_img, company_para, date_para]],
        colWidths=[1.5 * inch, avail_w - 1.5 * inch - 1.5 * inch, 1.5 * inch],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)

    # Blue rule under header
    rule_table = Table([[""]], colWidths=[avail_w])
    rule_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 2, sas_blue),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Spacer(1, 6))
    story.append(rule_table)
    story.append(Spacer(1, 10))

    # ── Report Title ──────────────────────────────────────────────────────
    story.append(Paragraph("Network Scan Report", style_title))

    # ── Scan Info ─────────────────────────────────────────────────────────
    info_lines = []
    if interface_name:
        info_lines.append(f"<b>Adapter:</b> {interface_name}")
    if interface_ip:
        info_lines.append(f"<b>IP Address:</b> {interface_ip}")
    info_lines.append(f"<b>Scan Date:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}")
    if scan_time:
        info_lines.append(f"<b>Scan Duration:</b> {scan_time}")
    info_lines.append(f"<b>Devices Found:</b> {len(devices)}")

    for line in info_lines:
        story.append(Paragraph(line, style_body))
    story.append(Spacer(1, 6))

    # ── Summary Stats ─────────────────────────────────────────────────────
    from core.mac_vendors import lookup_vendor_category

    auto_count = 0
    net_count = 0
    comp_count = 0
    other_count = 0
    eip_count = len(eip_identities)

    for d in devices:
        cat = "other"
        if d.ip_address in eip_identities:
            cat = "automation"
        elif d.mac_address:
            cat = lookup_vendor_category(d.mac_address)
        if cat == "automation":
            auto_count += 1
        elif cat == "networking":
            net_count += 1
        elif cat == "computing":
            comp_count += 1
        else:
            other_count += 1

    responding = sum(1 for d in devices if d.response_time_ms > 0 and d.response_time_ms < 20)
    slow = sum(1 for d in devices if d.response_time_ms >= 20)

    summary_data = [
        [Paragraph("<b>Total Devices</b>", style_cell),
         Paragraph(str(len(devices)), style_cell),
         Paragraph("<b>Automation</b>", style_cell),
         Paragraph(str(auto_count), style_cell),
         Paragraph("<b>Networking</b>", style_cell),
         Paragraph(str(net_count), style_cell),
         Paragraph("<b>Computing</b>", style_cell),
         Paragraph(str(comp_count), style_cell)],
        [Paragraph("<b>EtherNet/IP</b>", style_cell),
         Paragraph(str(eip_count), style_cell),
         Paragraph("<b>Responding &lt;20ms</b>", style_cell),
         Paragraph(str(responding), style_cell),
         Paragraph("<b>Slow/Issues</b>", style_cell),
         Paragraph(str(slow), style_cell),
         Paragraph("<b>Other</b>", style_cell),
         Paragraph(str(other_count), style_cell)],
    ]
    summary_col_w = avail_w / 8
    summary_table = Table(summary_data, colWidths=[summary_col_w] * 8)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F7F9FC")),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, border_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # ── Device Table ──────────────────────────────────────────────────────
    story.append(Paragraph("Device Inventory", style_heading))

    # Column headers
    col_headers = ["#", "IP Address", "MAC Address", "Vendor / Manufacturer",
                   "Product Name", "Type", "Ping (ms)", "Ports"]

    # Column widths (landscape letter = ~10" usable)
    col_widths = [
        0.3 * inch,    # #
        1.15 * inch,   # IP
        1.35 * inch,   # MAC
        1.9 * inch,    # Vendor
        2.2 * inch,    # Product
        1.1 * inch,    # Type
        0.65 * inch,   # Ping
        1.35 * inch,   # Ports
    ]

    # Build header row
    header_row = [Paragraph(h, style_header_cell) for h in col_headers]
    table_data = [header_row]

    # Build device rows
    for idx, device in enumerate(devices, 1):
        eip = eip_identities.get(device.ip_address)

        # Vendor: prefer EIP vendor, then MAC vendor
        vendor = ""
        if eip and eip.vendor_name:
            vendor = eip.vendor_name
        elif device.vendor:
            vendor = device.vendor
        elif device.device_type and device.device_type != "Unknown":
            vendor = device.device_type

        # Product name
        product = ""
        if device.product_name:
            product = device.product_name
        elif eip and eip.product_name:
            product = eip.product_name

        # Device type
        dev_type = ""
        if eip and eip.device_type_name:
            dev_type = eip.device_type_name
        elif device.device_type and device.device_type != "Unknown":
            if device.device_type != vendor:  # Don't duplicate vendor
                dev_type = device.device_type

        # Ping time
        ping_str = ""
        if device.response_time_ms > 0:
            if device.response_time_ms < 1:
                ping_str = "<1"
            else:
                ping_str = f"{device.response_time_ms:.0f}"
        elif not device.is_reachable:
            ping_str = "N/R"

        # Open ports
        ports_str = ""
        if device.open_ports:
            port_labels = []
            port_names = {
                44818: "EIP", 502: "Modbus", 80: "HTTP", 443: "HTTPS",
                22: "SSH", 23: "Telnet", 161: "SNMP", 2222: "EIP-cfg",
                8080: "HTTP-alt", 53: "DNS", 135: "RPC",
            }
            for p in sorted(device.open_ports)[:6]:  # Limit to 6
                label = port_names.get(p, str(p))
                port_labels.append(label)
            ports_str = ", ".join(port_labels)

        row = [
            Paragraph(str(idx), style_cell),
            Paragraph(f"<b>{device.ip_address}</b>", style_cell),
            Paragraph(device.mac_address or "—", style_cell),
            Paragraph(vendor or "Unknown", style_cell),
            Paragraph(product or "—", style_cell),
            Paragraph(dev_type or "—", style_cell),
            Paragraph(ping_str, style_cell),
            Paragraph(ports_str or "—", style_cell),
        ]
        table_data.append(row)

    # Build the table
    device_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Table styling
    table_style_cmds = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), sas_blue),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),

        # Grid
        ("BOX", (0, 0), (-1, -1), 0.75, sas_blue),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, sas_blue),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, border_color),

        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),

        # Number column right-aligned
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        # Ping column right-aligned
        ("ALIGN", (6, 0), (6, -1), "CENTER"),
    ]

    # Alternating row colors
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            table_style_cmds.append(
                ("BACKGROUND", (0, i), (-1, i), row_alt)
            )

    # Highlight slow-responding devices
    for i, device in enumerate(devices, 1):
        if device.response_time_ms >= 50:
            table_style_cmds.append(
                ("TEXTCOLOR", (6, i), (6, i), HexColor("#EF4444"))
            )
        elif device.response_time_ms >= 20:
            table_style_cmds.append(
                ("TEXTCOLOR", (6, i), (6, i), HexColor("#F59E0B"))
            )

    device_table.setStyle(TableStyle(table_style_cmds))
    story.append(device_table)

    # ── EIP Detail Section (if any EIP devices) ──────────────────────────
    eip_devices_list = [(ip, eid) for ip, eid in eip_identities.items()]
    if eip_devices_list:
        story.append(Spacer(1, 16))
        story.append(Paragraph("EtherNet/IP Device Details", style_heading))

        eip_headers = ["IP Address", "Vendor", "Product Name", "Firmware",
                       "Serial #", "Status"]
        eip_header_row = [Paragraph(h, style_header_cell) for h in eip_headers]

        eip_col_widths = [
            1.2 * inch, 1.6 * inch, 2.5 * inch,
            0.9 * inch, 1.1 * inch, 2.7 * inch,
        ]

        eip_table_data = [eip_header_row]
        for ip, eid in sorted(eip_devices_list, key=lambda x: tuple(
                int(p) for p in x[0].split("."))):
            eip_table_data.append([
                Paragraph(f"<b>{ip}</b>", style_cell),
                Paragraph(eid.vendor_name or "—", style_cell),
                Paragraph(eid.product_name or "—", style_cell),
                Paragraph(eid.firmware_version or "—", style_cell),
                Paragraph(eid.serial_hex or "—", style_cell),
                Paragraph(eid.status_description or "—", style_small),
            ])

        eip_table = Table(eip_table_data, colWidths=eip_col_widths, repeatRows=1)

        eip_style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), sas_orange),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("BOX", (0, 0), (-1, -1), 0.75, sas_orange),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, sas_orange),
            ("INNERGRID", (0, 1), (-1, -1), 0.25, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for i in range(1, len(eip_table_data)):
            if i % 2 == 0:
                eip_style_cmds.append(
                    ("BACKGROUND", (0, i), (-1, i), row_alt)
                )
        eip_table.setStyle(TableStyle(eip_style_cmds))
        story.append(eip_table)

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))

    # Thin rule
    footer_rule = Table([[""]], colWidths=[avail_w])
    footer_rule.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, border_color),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(footer_rule)
    story.append(Spacer(1, 4))

    footer_text = (
        f"Generated by SAS Network Diagnostic Tool v2.5.2  |  "
        f"Southern Automation Solutions  |  "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    story.append(Paragraph(footer_text, style_footer))

    # ── Build the PDF ─────────────────────────────────────────────────────
    def _add_page_numbers(canvas_obj, doc_obj):
        """Add page numbers to the footer of every page."""
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(HexColor(TEXT_SECONDARY_HEX))
        page_text = f"Page {doc_obj.page}"
        canvas_obj.drawRightString(
            page_w - 0.5 * inch, 0.35 * inch, page_text
        )
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=_add_page_numbers,
              onLaterPages=_add_page_numbers)

    logger.info(f"PDF report generated: {output_path} ({len(devices)} devices)")
    return output_path


# ── Packet Capture Report ─────────────────────────────────────────────────────

def _format_bytes(b: int) -> str:
    """Format byte count as human-readable string."""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    else:
        return f"{b / (1024 * 1024 * 1024):.2f} GB"


def generate_capture_report(
    analysis,
    interface_name: str = "",
    interface_ip: str = "",
    capture_file: str = "",
    output_path: str = "",
) -> str:
    """
    Generate a branded PDF packet capture analysis report.

    Args:
        analysis: CaptureAnalysis object from capture_analyzer
        interface_name: Name of the captured interface
        interface_ip: IP of the captured interface
        capture_file: Original .pcap filename
        output_path: Where to save the PDF

    Returns:
        Path to the generated PDF file
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, KeepTogether,
    )
    from reportlab.lib.colors import HexColor, white, black

    # ── Output path ───────────────────────────────────────────────────────
    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, f"Capture_Report_{timestamp}.pdf")

    # ── Colors ────────────────────────────────────────────────────────────
    sas_blue = HexColor(SAS_BLUE_HEX)
    sas_orange = HexColor(SAS_ORANGE_HEX)
    text_dark = HexColor(TEXT_DARK_HEX)
    text_secondary = HexColor(TEXT_SECONDARY_HEX)
    border_color = HexColor(BORDER_HEX)
    row_alt = HexColor(ROW_ALT_HEX)

    sev_colors = {
        "ok": HexColor("#22C55E"),
        "info": HexColor("#3B82F6"),
        "warning": HexColor("#F59E0B"),
        "critical": HexColor("#EF4444"),
    }

    # ── Page setup ────────────────────────────────────────────────────────
    page_w, page_h = letter
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.6 * inch,
    )

    # ── Styles ────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "Title2", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=18,
        textColor=sas_blue, spaceAfter=4,
    )
    style_heading = ParagraphStyle(
        "Heading", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=12,
        textColor=sas_blue, spaceBefore=14, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "Body2", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9,
        textColor=text_dark,
    )
    style_small = ParagraphStyle(
        "Small2", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=text_secondary,
    )
    style_cell = ParagraphStyle(
        "Cell2", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=text_dark, leading=10,
    )
    style_cell_bold = ParagraphStyle(
        "CellBold2", parent=style_cell,
        fontName="Helvetica-Bold",
    )
    style_header_cell = ParagraphStyle(
        "HeaderCell2", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=8,
        textColor=white, leading=10,
    )
    style_footer = ParagraphStyle(
        "Footer2", parent=styles["Normal"],
        fontName="Helvetica", fontSize=7,
        textColor=text_secondary, alignment=TA_CENTER,
    )
    style_finding_title = ParagraphStyle(
        "FindingTitle", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=9,
        textColor=text_dark, leading=12,
    )
    style_finding_body = ParagraphStyle(
        "FindingBody", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=text_secondary, leading=10, leftIndent=8,
    )

    avail_w = page_w - 1.2 * inch
    story = []

    # ── Header: Logo + Company Info ───────────────────────────────────────
    logo_path = _get_logo_path()
    now = datetime.now()

    if logo_path:
        try:
            logo_img = Image(logo_path, width=1.1 * inch, height=0.92 * inch)
        except Exception:
            logo_img = Paragraph(
                '<font name="Helvetica-Bold" size="14" color="{0}">SAS</font>'
                .format(SAS_BLUE_HEX), style_body)
    else:
        logo_img = Paragraph(
            '<font name="Helvetica-Bold" size="14" color="{0}">SAS</font>'
            .format(SAS_BLUE_HEX), style_body)

    company_text = (
        '<font name="Helvetica-Bold" size="12" color="{blue}">Southern Automation Solutions</font><br/>'
        '<font name="Helvetica" size="8" color="{gray}">111 Hemlock St. Ste A, Valdosta, GA 31601</font><br/>'
        '<font name="Helvetica" size="8" color="{gray}">Contact@SASControls.com  |  229-563-2897</font>'
    ).format(blue=SAS_BLUE_HEX, gray=TEXT_SECONDARY_HEX)
    company_para = Paragraph(company_text, style_body)

    date_text = (
        '<font name="Helvetica" size="8" color="{gray}">'
        '{date}<br/>{time}</font>'
    ).format(gray=TEXT_SECONDARY_HEX, date=now.strftime("%B %d, %Y"),
             time=now.strftime("%I:%M %p"))
    date_para = Paragraph(date_text, ParagraphStyle(
        "DR2", parent=style_body, alignment=TA_RIGHT))

    header_table = Table(
        [[logo_img, company_para, date_para]],
        colWidths=[1.3 * inch, avail_w - 1.3 * inch - 1.3 * inch, 1.3 * inch],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)

    # Blue rule
    rule = Table([[""]], colWidths=[avail_w])
    rule.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 2, sas_blue),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Spacer(1, 6))
    story.append(rule)
    story.append(Spacer(1, 10))

    # ── Report Title ──────────────────────────────────────────────────────
    story.append(Paragraph("Packet Capture Analysis Report", style_title))

    # ── Capture Info ──────────────────────────────────────────────────────
    info_lines = []
    if capture_file:
        info_lines.append(f"<b>Capture File:</b> {os.path.basename(capture_file)}")
    if interface_name:
        info_lines.append(f"<b>Interface:</b> {interface_name}")
    if interface_ip:
        info_lines.append(f"<b>IP Address:</b> {interface_ip}")
    info_lines.append(f"<b>Analysis Date:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}")
    for line in info_lines:
        story.append(Paragraph(line, style_body))
    story.append(Spacer(1, 8))

    # ── Health Score Banner ───────────────────────────────────────────────
    score = analysis.health_score
    if score >= 90:
        score_color = HexColor("#22C55E")
        score_label = "Excellent"
    elif score >= 70:
        score_color = HexColor("#84CC16")
        score_label = "Good"
    elif score >= 50:
        score_color = HexColor("#F59E0B")
        score_label = "Fair"
    elif score >= 30:
        score_color = HexColor("#F97316")
        score_label = "Poor"
    else:
        score_color = HexColor("#EF4444")
        score_label = "Critical"

    score_text = (
        f'<font name="Helvetica-Bold" size="22" color="{score_color.hexval()}">'
        f'{score}/100</font>  '
        f'<font name="Helvetica" size="11" color="{TEXT_SECONDARY_HEX}">'
        f'Network Health: {score_label}</font>'
    )
    story.append(Paragraph(score_text, style_body))
    story.append(Spacer(1, 8))

    # ── Summary Stats ─────────────────────────────────────────────────────
    story.append(Paragraph("Capture Summary", style_heading))

    summary_data = [
        [Paragraph("<b>Total Packets</b>", style_cell),
         Paragraph(f"{analysis.total_packets:,}", style_cell),
         Paragraph("<b>Total Bytes</b>", style_cell),
         Paragraph(_format_bytes(analysis.total_bytes), style_cell),
         Paragraph("<b>Duration</b>", style_cell),
         Paragraph(f"{analysis.duration_seconds:.1f}s", style_cell)],
        [Paragraph("<b>Unique Hosts</b>", style_cell),
         Paragraph(str(analysis.unique_hosts), style_cell),
         Paragraph("<b>Broadcast</b>", style_cell),
         Paragraph(f"{analysis.broadcast_pct:.1f}%", style_cell),
         Paragraph("<b>TCP Retransmissions</b>", style_cell),
         Paragraph(f"{analysis.tcp_retransmission_pct:.1f}%", style_cell)],
    ]
    scol_w = avail_w / 6
    summary_table = Table(summary_data, colWidths=[scol_w] * 6)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F7F9FC")),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, border_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)

    # ── Protocol Breakdown ────────────────────────────────────────────────
    if analysis.protocol_breakdown:
        story.append(Paragraph("Protocol Breakdown", style_heading))

        proto_headers = [
            Paragraph("Protocol", style_header_cell),
            Paragraph("Packets", style_header_cell),
            Paragraph("% of Total", style_header_cell),
        ]
        proto_data = [proto_headers]
        sorted_protos = sorted(analysis.protocol_breakdown.items(),
                               key=lambda x: -x[1])
        for proto, count in sorted_protos[:15]:
            pct = (count / analysis.total_packets * 100) if analysis.total_packets else 0
            proto_data.append([
                Paragraph(proto, style_cell_bold),
                Paragraph(f"{count:,}", style_cell),
                Paragraph(f"{pct:.1f}%", style_cell),
            ])

        pcol_widths = [avail_w * 0.45, avail_w * 0.28, avail_w * 0.27]
        proto_table = Table(proto_data, colWidths=pcol_widths, repeatRows=1)
        proto_style = [
            ("BACKGROUND", (0, 0), (-1, 0), sas_blue),
            ("BOX", (0, 0), (-1, -1), 0.75, sas_blue),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, sas_blue),
            ("INNERGRID", (0, 1), (-1, -1), 0.25, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]
        for i in range(1, len(proto_data)):
            if i % 2 == 0:
                proto_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
        proto_table.setStyle(TableStyle(proto_style))
        story.append(proto_table)

    # ── Top Talkers ───────────────────────────────────────────────────────
    if analysis.top_talkers_by_bytes:
        story.append(Paragraph("Top Talkers (by Bytes)", style_heading))

        talker_headers = [
            Paragraph("#", style_header_cell),
            Paragraph("IP Address", style_header_cell),
            Paragraph("Total Bytes", style_header_cell),
        ]
        talker_data = [talker_headers]
        for idx, (ip, bytes_val) in enumerate(analysis.top_talkers_by_bytes[:10], 1):
            talker_data.append([
                Paragraph(str(idx), style_cell),
                Paragraph(f"<b>{ip}</b>", style_cell),
                Paragraph(_format_bytes(bytes_val), style_cell),
            ])

        tcol_widths = [0.4 * inch, avail_w - 0.4 * inch - 1.5 * inch, 1.5 * inch]
        talker_table = Table(talker_data, colWidths=tcol_widths, repeatRows=1)
        talker_style = [
            ("BACKGROUND", (0, 0), (-1, 0), sas_orange),
            ("BOX", (0, 0), (-1, -1), 0.75, sas_orange),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, sas_orange),
            ("INNERGRID", (0, 1), (-1, -1), 0.25, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ]
        for i in range(1, len(talker_data)):
            if i % 2 == 0:
                talker_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
        talker_table.setStyle(TableStyle(talker_style))
        story.append(talker_table)

    # ── Diagnostic Findings ───────────────────────────────────────────────
    if analysis.findings:
        story.append(Paragraph("Diagnostic Findings", style_heading))

        for finding in analysis.findings:
            sev = finding.severity
            sev_color = sev_colors.get(sev, text_secondary)
            sev_label = sev.upper()

            # Severity badge + title
            title_text = (
                f'<font name="Helvetica-Bold" size="8" color="{sev_color.hexval()}">'
                f'[{sev_label}]</font>  '
                f'<font name="Helvetica-Bold" size="9" color="{TEXT_DARK_HEX}">'
                f'{finding.title}</font>'
            )

            finding_block = [Paragraph(title_text, style_finding_title)]
            if finding.summary:
                finding_block.append(
                    Paragraph(finding.summary, style_finding_body))
            if finding.explanation:
                finding_block.append(Spacer(1, 2))
                finding_block.append(Paragraph(
                    f"<b>What This Means:</b> {finding.explanation}",
                    style_finding_body))
            if finding.recommendation:
                finding_block.append(Spacer(1, 2))
                finding_block.append(Paragraph(
                    f"<b>Recommendation:</b> {finding.recommendation}",
                    style_finding_body))
            finding_block.append(Spacer(1, 6))

            # Keep each finding together
            story.append(KeepTogether(finding_block))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    footer_rule = Table([[""]], colWidths=[avail_w])
    footer_rule.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, border_color),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(footer_rule)
    story.append(Spacer(1, 4))

    footer_text = (
        f"Generated by SAS Network Diagnostic Tool v2.5.2  |  "
        f"Southern Automation Solutions  |  "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    story.append(Paragraph(footer_text, style_footer))

    # ── Build ─────────────────────────────────────────────────────────────
    def _add_page_numbers(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(HexColor(TEXT_SECONDARY_HEX))
        canvas_obj.drawRightString(
            page_w - 0.6 * inch, 0.35 * inch,
            f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=_add_page_numbers,
              onLaterPages=_add_page_numbers)

    logger.info(f"Capture report generated: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# Shared header builder
# ══════════════════════════════════════════════════════════════════════════════

def _build_report_header(story, styles_dict, title: str, info_lines: list,
                         page_w, inch_unit):
    """
    Build the standard SAS branded header used by all reports.
    Returns nothing — appends directly to story list.
    """
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.colors import HexColor

    sas_blue = HexColor(SAS_BLUE_HEX)

    logo_path = _get_logo_path()
    if logo_path:
        try:
            logo_img = Image(logo_path, width=1.3 * inch_unit, height=1.08 * inch_unit)
            logo_img.hAlign = "LEFT"
        except Exception:
            logo_img = Paragraph("SAS", styles_dict["company"])
    else:
        logo_img = Paragraph("SAS", styles_dict["company"])

    company_text = (
        '<font name="Helvetica-Bold" size="14" color="{blue}">Southern Automation Solutions</font><br/>'
        '<font name="Helvetica" size="8" color="{gray}">111 Hemlock St. Ste A, Valdosta, GA 31601</font><br/>'
        '<font name="Helvetica" size="8" color="{gray}">Contact@SASControls.com  |  229-563-2897</font>'
    ).format(blue=SAS_BLUE_HEX, gray=TEXT_SECONDARY_HEX)
    company_para = Paragraph(company_text, styles_dict["body"])

    from datetime import datetime
    now = datetime.now()
    date_text = (
        '<font name="Helvetica" size="8" color="{gray}">'
        '{date}<br/>{time}</font>'
    ).format(gray=TEXT_SECONDARY_HEX,
             date=now.strftime("%B %d, %Y"),
             time=now.strftime("%I:%M %p"))
    date_para = Paragraph(date_text, ParagraphStyle(
        "DateRight", parent=styles_dict["body"], alignment=TA_RIGHT))

    avail_w = page_w - 1.0 * inch_unit
    header_table = Table(
        [[logo_img, company_para, date_para]],
        colWidths=[1.5 * inch_unit, avail_w - 3.0 * inch_unit, 1.5 * inch_unit],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)

    # Blue rule
    rule_table = Table([[""]], colWidths=[avail_w])
    rule_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 2, sas_blue),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Spacer(1, 6))
    story.append(rule_table)
    story.append(Spacer(1, 10))

    # Title
    story.append(Paragraph(title, styles_dict["title"]))

    # Info lines
    for line in info_lines:
        story.append(Paragraph(line, styles_dict["body"]))
    story.append(Spacer(1, 6))


def _get_common_styles():
    """Return dict of common paragraph styles."""
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib.colors import HexColor, white

    styles = getSampleStyleSheet()
    sas_blue = HexColor(SAS_BLUE_HEX)
    text_dark = HexColor(TEXT_DARK_HEX)
    text_secondary = HexColor(TEXT_SECONDARY_HEX)

    return {
        "title": ParagraphStyle(
            "SASTitle2", parent=styles["Title"],
            fontName="Helvetica-Bold", fontSize=18,
            textColor=sas_blue, spaceAfter=4),
        "subtitle": ParagraphStyle(
            "SASSubtitle2", parent=styles["Normal"],
            fontName="Helvetica", fontSize=10,
            textColor=text_secondary, spaceAfter=2),
        "heading": ParagraphStyle(
            "SASHeading2", parent=styles["Heading2"],
            fontName="Helvetica-Bold", fontSize=12,
            textColor=sas_blue, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle(
            "SASBody2", parent=styles["Normal"],
            fontName="Helvetica", fontSize=9, textColor=text_dark),
        "small": ParagraphStyle(
            "SASSmall2", parent=styles["Normal"],
            fontName="Helvetica", fontSize=8, textColor=text_secondary),
        "cell": ParagraphStyle(
            "SASCell2", parent=styles["Normal"],
            fontName="Helvetica", fontSize=8, textColor=text_dark, leading=10),
        "cell_bold": ParagraphStyle(
            "SASCellBold2", parent=styles["Normal"],
            fontName="Helvetica-Bold", fontSize=8, textColor=text_dark, leading=10),
        "header_cell": ParagraphStyle(
            "SASHeaderCell2", parent=styles["Normal"],
            fontName="Helvetica-Bold", fontSize=8, textColor=white, leading=10),
        "company": ParagraphStyle(
            "SASCompany2", parent=styles["Normal"],
            fontName="Helvetica-Bold", fontSize=14,
            textColor=sas_blue, spaceAfter=2),
        "footer": ParagraphStyle(
            "SASFooter2", parent=styles["Normal"],
            fontName="Helvetica", fontSize=7,
            textColor=text_secondary, alignment=TA_CENTER),
    }


def _make_page_number_func(page_w, inch_unit):
    """Return a page-number callback for doc.build()."""
    from reportlab.lib.colors import HexColor

    def _add_page_numbers(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(HexColor(TEXT_SECONDARY_HEX))
        canvas_obj.drawRightString(
            page_w - 0.6 * inch_unit, 0.35 * inch_unit,
            f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    return _add_page_numbers


# ══════════════════════════════════════════════════════════════════════════════
# 3. Device Monitor PDF Report
# ══════════════════════════════════════════════════════════════════════════════

def generate_monitor_report(
    target_ip: str,
    stats,               # MonitorStats
    samples: list,        # List[PollSample]
    outages: list,        # List[OutageEvent]
    report=None,          # AnalysisReport (optional)
    output_path: str = "",
) -> str:
    """
    Generate a Device Monitor PDF report — documents the monitoring
    session for a single Ethernet device.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        KeepTogether,
    )

    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, f"Device_Monitor_{target_ip}_{timestamp}.pdf")

    sas_blue = HexColor(SAS_BLUE_HEX)
    header_bg = HexColor(HEADER_BG_HEX)
    row_alt = HexColor(ROW_ALT_HEX)
    text_dark = HexColor(TEXT_DARK_HEX)

    page_w, page_h = landscape(letter)
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.6 * inch)

    sd = _get_common_styles()
    story = []

    # Duration formatting
    dur_s = stats.duration_seconds if stats else 0
    if dur_s < 60:
        dur_str = f"{dur_s:.0f} seconds"
    elif dur_s < 3600:
        dur_str = f"{int(dur_s//60)}m {int(dur_s%60):02d}s"
    else:
        dur_str = f"{int(dur_s//3600)}h {int((dur_s%3600)//60):02d}m"

    # Header
    info_lines = [
        f"<b>Target Device:</b> {target_ip}",
        f"<b>Monitoring Duration:</b> {dur_str}",
        f"<b>Total Samples:</b> {stats.total_samples if stats else 0}",
        f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    _build_report_header(story, sd, "Device Monitor Report", info_lines, page_w, inch)

    # ── Summary Statistics Table ──
    story.append(Paragraph("Session Summary", sd["heading"]))
    if stats:
        summary_data = [
            [Paragraph("<b>Metric</b>", sd["header_cell"]),
             Paragraph("<b>Value</b>", sd["header_cell"]),
             Paragraph("<b>Metric</b>", sd["header_cell"]),
             Paragraph("<b>Value</b>", sd["header_cell"])],
            [Paragraph("Uptime", sd["cell"]),
             Paragraph(f"{stats.uptime_pct:.1f}%", sd["cell_bold"]),
             Paragraph("Outages", sd["cell"]),
             Paragraph(str(stats.outage_count), sd["cell_bold"])],
            [Paragraph("Ping Loss", sd["cell"]),
             Paragraph(f"{stats.ping_loss_pct:.1f}%", sd["cell_bold"]),
             Paragraph("Longest Outage", sd["cell"]),
             Paragraph(f"{stats.longest_outage_sec:.1f}s" if stats.longest_outage_sec > 0 else "None", sd["cell_bold"])],
            [Paragraph("Ping Avg", sd["cell"]),
             Paragraph(f"{stats.ping_avg_ms:.1f}ms" if stats.ping_avg_ms > 0 else "N/A", sd["cell_bold"]),
             Paragraph("Ping P95", sd["cell"]),
             Paragraph(f"{stats.ping_p95_ms:.1f}ms" if stats.ping_p95_ms > 0 else "N/A", sd["cell_bold"])],
            [Paragraph("Ping Min", sd["cell"]),
             Paragraph(f"{stats.ping_min_ms:.1f}ms" if stats.ping_min_ms > 0 else "N/A", sd["cell_bold"]),
             Paragraph("Ping Max", sd["cell"]),
             Paragraph(f"{stats.ping_max_ms:.1f}ms" if stats.ping_max_ms > 0 else "N/A", sd["cell_bold"])],
            [Paragraph("CIP Avg", sd["cell"]),
             Paragraph(f"{stats.cip_avg_ms:.1f}ms" if stats.cip_avg_ms > 0 else "N/A", sd["cell_bold"]),
             Paragraph("CIP Loss", sd["cell"]),
             Paragraph(f"{stats.cip_loss_pct:.1f}%" if stats.cip_sent > 0 else "N/A", sd["cell_bold"])],
        ]
        avail_w = page_w - 1.0 * inch
        cw = avail_w / 4
        t = Table(summary_data, colWidths=[cw] * 4)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor(ROW_WHITE_HEX)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor(BORDER_HEX)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # ── Health Score + Findings (if analysis was run) ──
    if report:
        story.append(Paragraph("Analysis Results", sd["heading"]))
        story.append(Paragraph(
            f"<b>Health Score:</b> {report.health_score}/100 — {report.health_label}",
            sd["body"]))
        if report.summary:
            story.append(Paragraph(report.summary, sd["body"]))
        story.append(Spacer(1, 6))

        if report.findings:
            for f in report.findings:
                sev = getattr(f, 'severity', 'info')
                icon = {"critical": "🔴", "warning": "🟡", "ok": "🟢"}.get(sev, "ℹ️")
                title_text = getattr(f, 'title', str(f))
                summary_text = getattr(f, 'summary', '')
                story.append(KeepTogether([
                    Paragraph(f"{icon} <b>{title_text}</b>", sd["cell_bold"]),
                    Paragraph(summary_text, sd["cell"]) if summary_text else Spacer(1, 1),
                    Spacer(1, 4),
                ]))
            story.append(Spacer(1, 6))

    # ── Outage Log ──
    if outages:
        story.append(Paragraph("Outage Events", sd["heading"]))
        outage_data = [
            [Paragraph("<b>#</b>", sd["header_cell"]),
             Paragraph("<b>Start Time</b>", sd["header_cell"]),
             Paragraph("<b>End Time</b>", sd["header_cell"]),
             Paragraph("<b>Duration</b>", sd["header_cell"]),
             Paragraph("<b>Recovery (ms)</b>", sd["header_cell"])],
        ]
        for i, o in enumerate(outages[:50], 1):
            start_str = o.start_time.strftime("%H:%M:%S") if o.start_time else "?"
            end_str = o.end_time.strftime("%H:%M:%S") if o.end_time else "ongoing"
            dur = f"{o.duration_seconds:.1f}s" if o.duration_seconds else "ongoing"
            rec = f"{o.recovery_time_ms:.1f}" if o.recovery_time_ms else "—"
            row_bg = row_alt if i % 2 == 0 else HexColor(ROW_WHITE_HEX)
            outage_data.append([
                Paragraph(str(i), sd["cell"]),
                Paragraph(start_str, sd["cell"]),
                Paragraph(end_str, sd["cell"]),
                Paragraph(dur, sd["cell_bold"]),
                Paragraph(rec, sd["cell"]),
            ])

        avail_w = page_w - 1.0 * inch
        t = Table(outage_data, colWidths=[0.4 * inch, 1.5 * inch, 1.5 * inch, 1.2 * inch, 1.2 * inch])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor(BORDER_HEX)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        t.setStyle(TableStyle(style_cmds))
        story.append(t)

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by SAS Network Diagnostics Tool  •  Southern Automation Solutions  •  www.SASControls.com",
        sd["footer"]))

    pn = _make_page_number_func(page_w, inch)
    doc.build(story, onFirstPage=pn, onLaterPages=pn)
    logger.info(f"Monitor report generated: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# 4. DeviceNet Scan PDF Report
# ══════════════════════════════════════════════════════════════════════════════

def generate_devicenet_scan_report(
    scan_result,          # DeviceNetScanResult
    output_path: str = "",
) -> str:
    """
    Generate a DeviceNet Scan PDF report — documents all discovered nodes.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        KeepTogether,
    )

    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, f"DeviceNet_Scan_{timestamp}.pdf")

    sas_blue = HexColor(SAS_BLUE_HEX)
    header_bg = HexColor(HEADER_BG_HEX)
    row_alt = HexColor(ROW_ALT_HEX)

    page_w, page_h = landscape(letter)
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.6 * inch)

    sd = _get_common_styles()
    story = []

    online_nodes = [n for n in scan_result.nodes if n.is_online]
    offline_count = 64 - len(online_nodes)

    info_lines = [
        f"<b>Connection Method:</b> {scan_result.connection_method}",
        f"<b>PLC IP:</b> {scan_result.plc_ip}" if scan_result.plc_ip else "",
        f"<b>Scanner Slot:</b> {scan_result.scanner_slot}" if scan_result.scanner_slot >= 0 else "",
        f"<b>Nodes Online:</b> {scan_result.nodes_online} / 64",
        f"<b>Scan Time:</b> {scan_result.scan_time_seconds:.1f} seconds",
        f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    info_lines = [l for l in info_lines if l]
    _build_report_header(story, sd, "DeviceNet Scan Report", info_lines, page_w, inch)

    # ── Scanner Diagnostics ──
    diag = scan_result.scanner_diag
    if diag:
        story.append(Paragraph("Scanner Module", sd["heading"]))
        diag_data = [
            [Paragraph("<b>Property</b>", sd["header_cell"]),
             Paragraph("<b>Value</b>", sd["header_cell"])],
            [Paragraph("Product", sd["cell"]),
             Paragraph(diag.scanner_product_name or "—", sd["cell_bold"])],
            [Paragraph("MAC ID", sd["cell"]),
             Paragraph(str(diag.scanner_mac_id), sd["cell_bold"])],
            [Paragraph("Baud Rate", sd["cell"]),
             Paragraph(diag.scanner_baud_rate or "—", sd["cell_bold"])],
            [Paragraph("Vendor", sd["cell"]),
             Paragraph(diag.scanner_vendor or "—", sd["cell"])],
            [Paragraph("Serial", sd["cell"]),
             Paragraph(diag.scanner_serial or "—", sd["cell"])],
            [Paragraph("Revision", sd["cell"]),
             Paragraph(diag.scanner_revision or "—", sd["cell"])],
            [Paragraph("Status", sd["cell"]),
             Paragraph(diag.scanner_status_text or "—", sd["cell"])],
            [Paragraph("Bus Off Count", sd["cell"]),
             Paragraph(str(diag.bus_off_count), sd["cell_bold"])],
        ]
        t = Table(diag_data, colWidths=[2.0 * inch, 4.0 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor(BORDER_HEX)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # ── Online Nodes Table ──
    if online_nodes:
        story.append(Paragraph(f"Online Nodes ({len(online_nodes)})", sd["heading"]))
        node_data = [
            [Paragraph("<b>MAC</b>", sd["header_cell"]),
             Paragraph("<b>Product Name</b>", sd["header_cell"]),
             Paragraph("<b>Vendor</b>", sd["header_cell"]),
             Paragraph("<b>Type</b>", sd["header_cell"]),
             Paragraph("<b>Revision</b>", sd["header_cell"]),
             Paragraph("<b>Serial</b>", sd["header_cell"]),
             Paragraph("<b>Status</b>", sd["header_cell"]),
             Paragraph("<b>RT (ms)</b>", sd["header_cell"])],
        ]
        for n in sorted(online_nodes, key=lambda x: x.mac_id):
            rev = f"{n.revision_major}.{n.revision_minor:03d}" if n.revision_major else "—"
            node_data.append([
                Paragraph(str(n.mac_id), sd["cell_bold"]),
                Paragraph(n.product_name or "—", sd["cell"]),
                Paragraph(n.vendor_name or "—", sd["cell"]),
                Paragraph(n.product_type_name or "—", sd["cell"]),
                Paragraph(rev, sd["cell"]),
                Paragraph(n.serial_number or "—", sd["cell"]),
                Paragraph(n.status_text or "—", sd["cell"]),
                Paragraph(f"{n.response_time_ms:.0f}" if n.response_time_ms else "—", sd["cell"]),
            ])

        avail_w = page_w - 1.0 * inch
        t = Table(node_data, colWidths=[
            0.4 * inch, 2.0 * inch, 2.0 * inch, 1.5 * inch,
            0.7 * inch, 1.2 * inch, 1.2 * inch, 0.6 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor(BORDER_HEX)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    # ── Errors ──
    if scan_result.errors:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Scan Errors / Warnings", sd["heading"]))
        for err in scan_result.errors:
            story.append(Paragraph(f"⚠ {err}", sd["body"]))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by SAS Network Diagnostics Tool  •  Southern Automation Solutions  •  www.SASControls.com",
        sd["footer"]))

    pn = _make_page_number_func(page_w, inch)
    doc.build(story, onFirstPage=pn, onLaterPages=pn)
    logger.info(f"DeviceNet scan report generated: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# 5. DeviceNet Network Monitor PDF Report
# ══════════════════════════════════════════════════════════════════════════════

def generate_devicenet_monitor_report(
    stats,                # DeviceNetMonitorStats
    report=None,          # DeviceNetAnalysisReport (optional)
    connection_info: str = "",
    output_path: str = "",
) -> str:
    """
    Generate a DeviceNet Network Monitor PDF report — documents
    a monitoring session across all DeviceNet nodes.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        KeepTogether,
    )

    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, f"DeviceNet_Monitor_{timestamp}.pdf")

    sas_blue = HexColor(SAS_BLUE_HEX)
    header_bg = HexColor(HEADER_BG_HEX)
    row_alt = HexColor(ROW_ALT_HEX)

    page_w, page_h = landscape(letter)
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.6 * inch)

    sd = _get_common_styles()
    story = []

    # Duration
    dur_s = stats.duration_seconds if stats else 0
    if dur_s < 60:
        dur_str = f"{dur_s:.0f} seconds"
    elif dur_s < 3600:
        dur_str = f"{int(dur_s//60)}m {int(dur_s%60):02d}s"
    else:
        dur_str = f"{int(dur_s//3600)}h {int((dur_s%3600)//60):02d}m"

    info_lines = [
        f"<b>Connection:</b> {connection_info}" if connection_info else "",
        f"<b>Monitoring Duration:</b> {dur_str}",
        f"<b>Total Cycles:</b> {stats.total_cycles if stats else 0}",
        f"<b>Monitored Nodes:</b> {stats.monitored_nodes if stats else 0}",
        f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    info_lines = [l for l in info_lines if l]
    _build_report_header(story, sd, "DeviceNet Network Monitor Report", info_lines, page_w, inch)

    # ── Summary ──
    if stats:
        story.append(Paragraph("Session Summary", sd["heading"]))
        summary_data = [
            [Paragraph("<b>Metric</b>", sd["header_cell"]),
             Paragraph("<b>Value</b>", sd["header_cell"]),
             Paragraph("<b>Metric</b>", sd["header_cell"]),
             Paragraph("<b>Value</b>", sd["header_cell"])],
            [Paragraph("Network Uptime", sd["cell"]),
             Paragraph(f"{stats.network_uptime_pct:.1f}%", sd["cell_bold"]),
             Paragraph("Total Events", sd["cell"]),
             Paragraph(str(stats.total_events), sd["cell_bold"])],
            [Paragraph("Cycles All Online", sd["cell"]),
             Paragraph(str(stats.cycles_all_online), sd["cell_bold"]),
             Paragraph("Critical Events", sd["cell"]),
             Paragraph(str(stats.critical_events), sd["cell_bold"])],
            [Paragraph("Cycles w/ Dropouts", sd["cell"]),
             Paragraph(str(stats.cycles_with_dropouts), sd["cell_bold"]),
             Paragraph("Bus Off Count", sd["cell"]),
             Paragraph(str(stats.bus_off_total), sd["cell_bold"])],
        ]
        avail_w = page_w - 1.0 * inch
        cw = avail_w / 4
        t = Table(summary_data, colWidths=[cw] * 4)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor(BORDER_HEX)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # ── Per-Node Health ──
    if stats and stats.node_histories:
        story.append(Paragraph("Node Health Summary", sd["heading"]))
        node_data = [
            [Paragraph("<b>MAC</b>", sd["header_cell"]),
             Paragraph("<b>Product</b>", sd["header_cell"]),
             Paragraph("<b>Uptime %</b>", sd["header_cell"]),
             Paragraph("<b>Online</b>", sd["header_cell"]),
             Paragraph("<b>Offline</b>", sd["header_cell"]),
             Paragraph("<b>Dropouts</b>", sd["header_cell"])],
        ]
        for mac_id in sorted(stats.node_histories.keys()):
            nh = stats.node_histories[mac_id]
            online = getattr(nh, 'online_count', 0)
            total = getattr(nh, 'total_count', 0) or 1
            offline = total - online
            dropouts = getattr(nh, 'dropout_count', 0)
            uptime_pct = (online / total * 100) if total else 0
            product = getattr(nh, 'product_name', '') or '—'
            node_data.append([
                Paragraph(str(mac_id), sd["cell_bold"]),
                Paragraph(product, sd["cell"]),
                Paragraph(f"{uptime_pct:.1f}%", sd["cell_bold"]),
                Paragraph(str(online), sd["cell"]),
                Paragraph(str(offline), sd["cell"]),
                Paragraph(str(dropouts), sd["cell_bold"]),
            ])

        t = Table(node_data, colWidths=[0.5 * inch, 2.5 * inch, 1.0 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor(BORDER_HEX)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    # ── Analysis Findings ──
    if report and hasattr(report, 'findings') and report.findings:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Analysis Findings", sd["heading"]))
        if hasattr(report, 'health_score'):
            label = getattr(report, 'health_label', '')
            story.append(Paragraph(
                f"<b>Network Health Score:</b> {report.health_score}/100 — {label}",
                sd["body"]))
            story.append(Spacer(1, 4))
        for f in report.findings:
            sev = getattr(f, 'severity', 'info')
            icon = {"critical": "🔴", "warning": "🟡", "ok": "🟢"}.get(sev, "ℹ️")
            title_text = getattr(f, 'title', str(f))
            summary_text = getattr(f, 'summary', '')
            story.append(KeepTogether([
                Paragraph(f"{icon} <b>{title_text}</b>", sd["cell_bold"]),
                Paragraph(summary_text, sd["cell"]) if summary_text else Spacer(1, 1),
                Spacer(1, 4),
            ]))

    # ── Problematic Nodes ──
    if stats and stats.most_problematic_nodes:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Most Problematic Nodes", sd["heading"]))
        for mac_id, issue in stats.most_problematic_nodes:
            story.append(Paragraph(f"⚠ <b>MAC {mac_id}:</b> {issue}", sd["body"]))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by SAS Network Diagnostics Tool  •  Southern Automation Solutions  •  www.SASControls.com",
        sd["footer"]))

    pn = _make_page_number_func(page_w, inch)
    doc.build(story, onFirstPage=pn, onLaterPages=pn)
    logger.info(f"DeviceNet monitor report generated: {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# Device Diagnostic Report
# ═══════════════════════════════════════════════════════════════════════════════

def generate_device_diagnostic_report(
    device,                # DiscoveredDevice
    eip_identity=None,     # EIPIdentity (optional)
    diagnostics=None,      # EthernetDiagnostics (optional)
    report=None,           # DiagnosticReport
    output_path: str = "",
) -> str:
    """
    Generate a branded PDF diagnostic report for a single device.
    Includes health score, findings, and recommendations.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        KeepTogether,
    )

    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        safe_ip = (device.ip_address or "unknown").replace(".", "_")
        output_path = os.path.join(docs_dir, f"Device_Diagnostic_{safe_ip}_{timestamp}.pdf")

    sas_blue = HexColor(SAS_BLUE_HEX)
    header_bg = HexColor(HEADER_BG_HEX)
    row_alt = HexColor(ROW_ALT_HEX)
    text_dark = HexColor(TEXT_DARK_HEX)
    border = HexColor(BORDER_HEX)

    page_w, page_h = letter
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.6 * inch)

    sd = _get_common_styles()
    story = []

    # Device info
    dev_name = getattr(device, "display_name", device.ip_address) if device else "Unknown"
    dev_ip = getattr(device, "ip_address", "") if device else ""
    dev_mac = getattr(device, "mac_address", "") if device else ""
    dev_vendor = getattr(device, "vendor", "") if device else ""

    # Header
    info_lines = [
        f"<b>Device:</b> {dev_name}",
        f"<b>IP Address:</b> {dev_ip}",
        f"<b>MAC Address:</b> {dev_mac}" if dev_mac else "",
        f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    info_lines = [l for l in info_lines if l]
    _build_report_header(story, sd, "Device Diagnostic Report", info_lines, page_w, inch)

    # ── Health Score ──
    if report:
        score = report.health_score
        if score >= 80:
            score_color = "#22C55E"
            score_label = "HEALTHY"
        elif score >= 50:
            score_color = "#F59E0B"
            score_label = "WARNING"
        else:
            score_color = "#EF4444"
            score_label = "CRITICAL"

        story.append(Paragraph("Health Assessment", sd["heading"]))
        health_data = [
            [Paragraph("<b>Health Score</b>", sd["header_cell"]),
             Paragraph("<b>Status</b>", sd["header_cell"]),
             Paragraph("<b>Problems</b>", sd["header_cell"]),
             Paragraph("<b>Warnings</b>", sd["header_cell"]),
             Paragraph("<b>OK</b>", sd["header_cell"])],
            [Paragraph(f"<b>{score}/100</b>", sd["cell_bold"]),
             Paragraph(f"<b>{score_label}</b>", sd["cell_bold"]),
             Paragraph(str(report.critical_count), sd["cell"]),
             Paragraph(str(report.warning_count), sd["cell"]),
             Paragraph(str(report.ok_count), sd["cell"])],
        ]
        avail_w = page_w - 1.0 * inch
        cw = avail_w / 5
        t = Table(health_data, colWidths=[cw] * 5)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("GRID", (0, 0), (-1, -1), 0.5, border),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

        # Overall summary
        if report.overall_summary:
            story.append(Paragraph("Summary", sd["heading"]))
            story.append(Paragraph(report.overall_summary, sd["body"]))
            story.append(Spacer(1, 12))

    # ── Device Details ──
    if eip_identity or device:
        story.append(Paragraph("Device Information", sd["heading"]))
        detail_rows = [[
            Paragraph("<b>Property</b>", sd["header_cell"]),
            Paragraph("<b>Value</b>", sd["header_cell"]),
        ]]
        details = [
            ("IP Address", dev_ip),
            ("MAC Address", dev_mac),
            ("Vendor", dev_vendor),
        ]
        if eip_identity:
            details.extend([
                ("Product Name", getattr(eip_identity, "product_name", "")),
                ("Product Code", str(getattr(eip_identity, "product_code", ""))),
                ("Device Type", str(getattr(eip_identity, "device_type_name", ""))),
                ("Revision", str(getattr(eip_identity, "revision", ""))),
                ("Serial Number", str(getattr(eip_identity, "serial_hex", ""))),
            ])
        for prop, val in details:
            if val:
                detail_rows.append([
                    Paragraph(prop, sd["cell"]),
                    Paragraph(str(val), sd["cell_bold"]),
                ])
        cw1 = avail_w * 0.3
        cw2 = avail_w * 0.7
        t = Table(detail_rows, colWidths=[cw1, cw2])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
            ("GRID", (0, 0), (-1, -1), 0.5, border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

    # ── Findings ──
    if report and report.findings:
        story.append(Paragraph("Diagnostic Findings", sd["heading"]))

        severity_order = {"critical": 0, "warning": 1, "ok": 2, "info": 3}
        sorted_findings = sorted(report.findings,
                                  key=lambda f: severity_order.get(f.severity.value, 4))

        severity_colors = {
            "critical": HexColor("#FEE2E2"),
            "warning": HexColor("#FEF3C7"),
            "ok": HexColor("#DCFCE7"),
            "info": HexColor("#DBEAFE"),
        }
        severity_labels = {
            "critical": "🔴 PROBLEM",
            "warning": "⚠️ WARNING",
            "ok": "✅ OK",
            "info": "ℹ️ INFO",
        }

        for finding in sorted_findings:
            sev = finding.severity.value
            bg_color = severity_colors.get(sev, row_alt)
            label = severity_labels.get(sev, sev.upper())

            finding_data = [
                [Paragraph(f"<b>{label}: {finding.title}</b>", sd["cell_bold"])],
                [Paragraph(finding.summary, sd["cell"])],
            ]
            if finding.explanation:
                finding_data.append([Paragraph(f"<i>{finding.explanation}</i>", sd["cell"])])
            if finding.recommendation:
                finding_data.append([Paragraph(f"<b>Action:</b> {finding.recommendation}", sd["cell"])])
            if finding.raw_value:
                finding_data.append([Paragraph(f"<font size=7 color='#666666'>Raw: {finding.raw_value}</font>", sd["cell"])])

            t = Table(finding_data, colWidths=[avail_w])
            styles = [
                ("BACKGROUND", (0, 0), (0, 0), bg_color),
                ("GRID", (0, 0), (-1, -1), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
            t.setStyle(TableStyle(styles))
            story.append(KeepTogether([t, Spacer(1, 6)]))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by SAS Network Diagnostics Tool  •  Southern Automation Solutions  •  www.SASControls.com",
        sd["footer"]))

    pn = _make_page_number_func(page_w, inch)
    doc.build(story, onFirstPage=pn, onLaterPages=pn)
    logger.info(f"Device diagnostic report generated: {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-Device Monitor Report
# ═══════════════════════════════════════════════════════════════════════════════

def generate_multi_monitor_report(
    targets: list,                   # List[DeviceTarget]
    analytics: dict,                 # Dict[str, DeviceAnalytics]
    elapsed_seconds: float = 0,
    sample_count: int = 0,
    chart_image_path: str = "",      # Path to trend chart PNG
    output_path: str = "",
) -> str:
    """
    Generate a branded PDF report for multi-device monitoring session.
    Includes trend chart image and per-device analytics.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        KeepTogether, Image as RLImage,
    )

    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, f"MultiMonitor_Report_{timestamp}.pdf")

    sas_blue = HexColor(SAS_BLUE_HEX)
    header_bg = HexColor(HEADER_BG_HEX)
    row_alt = HexColor(ROW_ALT_HEX)
    text_dark = HexColor(TEXT_DARK_HEX)
    border = HexColor(BORDER_HEX)

    page_w, page_h = landscape(letter)
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.6 * inch)

    sd = _get_common_styles()
    story = []

    # Duration formatting
    if elapsed_seconds < 60:
        dur_str = f"{elapsed_seconds:.0f} seconds"
    elif elapsed_seconds < 3600:
        dur_str = f"{int(elapsed_seconds // 60)}m {int(elapsed_seconds % 60):02d}s"
    else:
        dur_str = f"{int(elapsed_seconds // 3600)}h {int((elapsed_seconds % 3600) // 60):02d}m"

    # Header
    info_lines = [
        f"<b>Devices Monitored:</b> {len(targets)}",
        f"<b>Monitoring Duration:</b> {dur_str}",
        f"<b>Total Samples:</b> {sample_count:,}",
        f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    _build_report_header(story, sd, "Multi-Device Monitor Report", info_lines, page_w, inch)

    # ── Trend Chart Image ──
    if chart_image_path and os.path.isfile(chart_image_path):
        story.append(Paragraph("Response Time Trend", sd["heading"]))
        try:
            chart_w = page_w - 1.0 * inch
            chart_h = chart_w * 0.4
            img = RLImage(chart_image_path, width=chart_w, height=chart_h)
            story.append(img)
            story.append(Spacer(1, 12))
        except Exception as e:
            logger.warning(f"Could not embed chart image: {e}")

    # ── Per-Device Analytics Table ──
    story.append(Paragraph("Device Analytics", sd["heading"]))

    table_header = [
        Paragraph("<b>Device</b>", sd["header_cell"]),
        Paragraph("<b>IP Address</b>", sd["header_cell"]),
        Paragraph("<b>Uptime %</b>", sd["header_cell"]),
        Paragraph("<b>Ping Avg</b>", sd["header_cell"]),
        Paragraph("<b>Ping Min</b>", sd["header_cell"]),
        Paragraph("<b>Ping Max</b>", sd["header_cell"]),
        Paragraph("<b>Ping Loss</b>", sd["header_cell"]),
        Paragraph("<b>CIP Avg</b>", sd["header_cell"]),
        Paragraph("<b>Outages</b>", sd["header_cell"]),
        Paragraph("<b>Longest</b>", sd["header_cell"]),
        Paragraph("<b>Product</b>", sd["header_cell"]),
    ]
    table_data = [table_header]

    for t in targets:
        a = analytics.get(t.ip)
        if not a:
            continue

        if a.longest_outage_sec > 0:
            if a.longest_outage_sec < 60:
                longest = f"{a.longest_outage_sec:.1f}s"
            else:
                longest = f"{int(a.longest_outage_sec // 60)}m {int(a.longest_outage_sec % 60):02d}s"
        else:
            longest = "None"

        row = [
            Paragraph(t.display_name, sd["cell"]),
            Paragraph(t.ip, sd["cell"]),
            Paragraph(f"{a.uptime_pct:.1f}%", sd["cell_bold"]),
            Paragraph(f"{a.ping_avg_ms:.1f}ms" if a.ping_avg_ms > 0 else "—", sd["cell"]),
            Paragraph(f"{a.ping_min_ms:.1f}ms" if a.ping_min_ms > 0 else "—", sd["cell"]),
            Paragraph(f"{a.ping_max_ms:.1f}ms" if a.ping_max_ms > 0 else "—", sd["cell"]),
            Paragraph(f"{a.ping_loss_pct:.1f}%", sd["cell"]),
            Paragraph(f"{a.cip_avg_ms:.1f}ms" if a.cip_avg_ms > 0 else "—", sd["cell"]),
            Paragraph(str(a.outage_count), sd["cell"]),
            Paragraph(longest, sd["cell"]),
            Paragraph(a.product_name or "—", sd["cell"]),
        ]
        table_data.append(row)

    avail_w = page_w - 1.0 * inch
    col_widths = [avail_w * p for p in [0.10, 0.11, 0.07, 0.08, 0.08, 0.08, 0.07, 0.08, 0.06, 0.08, 0.19]]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
        ("GRID", (0, 0), (-1, -1), 0.5, border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # ── Summary Statistics ──
    total_devices = len(targets)
    devices_online = sum(1 for t in targets
                          if analytics.get(t.ip) and analytics[t.ip].last_status == "online")
    avg_uptime = 0.0
    if analytics:
        uptimes = [a.uptime_pct for a in analytics.values()]
        avg_uptime = sum(uptimes) / len(uptimes) if uptimes else 0

    story.append(Paragraph("Session Summary", sd["heading"]))
    summary_data = [
        [Paragraph("<b>Metric</b>", sd["header_cell"]),
         Paragraph("<b>Value</b>", sd["header_cell"]),
         Paragraph("<b>Metric</b>", sd["header_cell"]),
         Paragraph("<b>Value</b>", sd["header_cell"])],
        [Paragraph("Total Devices", sd["cell"]),
         Paragraph(str(total_devices), sd["cell_bold"]),
         Paragraph("Devices Online (final)", sd["cell"]),
         Paragraph(str(devices_online), sd["cell_bold"])],
        [Paragraph("Average Uptime", sd["cell"]),
         Paragraph(f"{avg_uptime:.1f}%", sd["cell_bold"]),
         Paragraph("Total Samples", sd["cell"]),
         Paragraph(f"{sample_count:,}", sd["cell_bold"])],
    ]
    cw = avail_w / 4
    t = Table(summary_data, colWidths=[cw] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(ROW_WHITE_HEX), row_alt]),
        ("GRID", (0, 0), (-1, -1), 0.5, border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by SAS Network Diagnostics Tool  •  Southern Automation Solutions  •  www.SASControls.com",
        sd["footer"]))

    pn = _make_page_number_func(page_w, inch)
    doc.build(story, onFirstPage=pn, onLaterPages=pn)
    logger.info(f"Multi-monitor report generated: {output_path}")
    return output_path
