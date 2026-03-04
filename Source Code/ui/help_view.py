"""
SAS Network Diagnostics Tool — Help View
Detailed descriptions and step-by-step instructions for every tool.
"""

import logging
import customtkinter as ctk
from ui.theme import *
from ui.widgets import enable_touch_scroll

logger = logging.getLogger(__name__)


# ── Help Content ──────────────────────────────────────────────────────────────

HELP_SECTIONS = [
    {
        "icon": "🔍",
        "title": "Network Scanner",
        "description": (
            "The Network Scanner discovers all devices on your currently connected "
            "Ethernet subnet. It performs a comprehensive scan that includes ICMP ping "
            "sweeps, ARP table harvesting, EtherNet/IP ListIdentity broadcasts, and "
            "common port checks. Devices are identified by IP, MAC address, vendor "
            "(OUI lookup), and EtherNet/IP identity data when available.\n\n"
            "This tool is designed for networks where your laptop is already configured "
            "on the correct subnet. It shows all active hosts on that subnet, with "
            "special emphasis on automation devices (Allen-Bradley, Siemens, Schneider, "
            "etc.). Click any device to see detailed identity information including "
            "product name, firmware revision, serial number, and device status."
        ),
        "steps": [
            "Connect your laptop to the industrial network with an Ethernet cable.",
            "Make sure your adapter is configured with an IP address on the correct "
            "subnet, or set to DHCP if the network has a DHCP server.",
            "Select the correct network adapter from the dropdown at the top.",
            "Click 'Scan Network' to begin the scan. The progress bar shows which "
            "phase is active (ping sweep → ARP harvest → EtherNet/IP broadcast → "
            "port scan).",
            "Results appear in real-time as devices are discovered. Automation devices "
            "are sorted to the top.",
            "Click any device row to open the Device Detail view with full identity "
            "data, CIP attributes, and diagnostics.",
            "Use the 'Export CSV' button to save the scan results for documentation.",
        ],
    },
    {
        "icon": "📡",
        "title": "Device Finder",
        "description": (
            "The Device Finder locates devices on the wire even when your laptop is on "
            "a completely different subnet. This is the tool to use when you plug into "
            "an unknown network and need to figure out what's there and what IP ranges "
            "are in use.\n\n"
            "It works by probing all common factory-default IP ranges used by major "
            "automation vendors (Allen-Bradley, Siemens, Schneider, Beckhoff, WAGO, "
            "Phoenix Contact, Moxa, and more), sending EtherNet/IP ListIdentity "
            "broadcasts, and performing ARP-level discovery. For each device found, "
            "it tells you the device's IP, MAC address, vendor/manufacturer, and — "
            "critically — what subnet settings you need to configure on your laptop "
            "to communicate with that device.\n\n"
            "You can also add custom subnet ranges to scan. This is useful when devices "
            "have been configured to non-standard IP ranges that aren't in the common "
            "defaults list."
        ),
        "steps": [
            "Connect your laptop to the network with an Ethernet cable.",
            "Set your adapter to DHCP / Automatic. You do NOT need to be on the same "
            "subnet as the devices — that's the whole point of this tool.",
            "Select the correct network adapter from the dropdown.",
            "Check 'Scan common factory subnets' to probe all known default ranges "
            "(192.168.1.x, 10.10.0.x, etc.).",
            "Optionally, check 'Scan custom subnet ranges' and enter any additional "
            "subnets to probe. Enter one per line in CIDR notation (e.g. 10.50.100.0/24). "
            "This is useful for networks with non-standard IP addressing.",
            "Click 'Discover Devices' to start. The scan takes 30-90 seconds depending "
            "on how many ranges are being probed.",
            "Results show each device with its IP, MAC, vendor, and the EtherNet/IP "
            "identity if it responded.",
            "The 'Suggested Settings' column tells you exactly what static IP and subnet "
            "mask to set on your laptop to communicate with each device.",
            "Click the copy button (📋) next to any device to copy its suggested IP "
            "settings to clipboard.",
        ],
    },
    {
        "icon": "📊",
        "title": "Ethernet Device Monitor",
        "description": (
            "The Ethernet Device Monitor locks onto a single Ethernet/IP device and "
            "continuously monitors its availability, response time, and CIP status "
            "over time. It's designed to catch intermittent network problems that are "
            "impossible to find with a single ping or scan.\n\n"
            "The monitor uses a dual-probe approach: ICMP ping and CIP ListIdentity "
            "requests run in parallel at each poll cycle. This means it can detect "
            "problems at both the IP layer (cable, switch, IP config) and the "
            "application layer (CIP stack crash, device overload, firmware bug).\n\n"
            "After collecting data, the built-in analyzer examines the samples for "
            "over 15 diagnostic patterns including periodic dropout detection, "
            "time-of-day correlation, response time degradation, burst errors, "
            "jitter analysis, and outage pattern classification. It produces a "
            "plain-language report with likely causes and specific troubleshooting "
            "steps.\n\n"
            "The response time chart auto-scales both axes and includes a timeline "
            "slider so you can scroll back through the entire monitoring session to "
            "see exactly when events occurred."
        ),
        "steps": [
            "Enter the IP address of the device you want to monitor.",
            "Select the poll interval. Use 1-2 seconds for active troubleshooting, "
            "5-10 seconds for longer monitoring sessions, 30-60 seconds for overnight runs.",
            "Enable or disable Ping and CIP probes using the checkboxes. Both are "
            "recommended for the most complete picture.",
            "Click 'Start Monitor' to begin continuous polling.",
            "Watch the live response time chart — green line is ping, blue is CIP, "
            "red markers indicate failures.",
            "The stats cards update in real-time: uptime percentage, packet loss, "
            "average response time, outage count, and samples collected.",
            "The Event Log shows each online/offline transition as it happens.",
            "Let the monitor run for at least 15-30 minutes, or longer if the problem "
            "is intermittent. For shift-long or overnight monitoring, use a longer "
            "poll interval (30-60 seconds) to keep the dataset manageable.",
            "Use the timeline slider below the chart to scroll back through history. "
            "Click '▶ LIVE' to snap back to real-time.",
            "Click 'Stop Monitor' when you have enough data.",
            "Click 'Analyze' to run the pattern detection engine. A detailed report "
            "appears below with findings, likely causes, and specific recommendations.",
            "Click 'Export CSV' to save the raw data for documentation or further "
            "analysis in Excel.",
        ],
    },
    {
        "icon": "🔎",
        "title": "Port Scanner",
        "description": (
            "The Port Scanner tests specific TCP ports on a target device to determine "
            "which services are running and accessible. It identifies well-known "
            "industrial services like EtherNet/IP (44818), Modbus TCP (502), Siemens "
            "S7 (102), OPC UA (4840), and many more.\n\n"
            "Results show each port as open, closed, or filtered. Open ports have "
            "the service identified. The scanner also performs banner grabbing on "
            "open ports to show additional information like web server versions."
        ),
        "steps": [
            "Enter the target device's IP address.",
            "Enter the ports to scan — type individual ports (80, 443, 502), "
            "ranges (1-1024), or use one of the preset buttons.",
            "Set the timeout (default 1000ms — increase for slow networks).",
            "Click 'Scan Ports' to begin. Results appear in real-time.",
            "Open ports are shown in green, closed in red, filtered in yellow.",
            "The service column identifies known protocols for each port.",
        ],
    },
    {
        "icon": "🔌",
        "title": "TCP/UDP Socket Tester",
        "description": (
            "The Socket Tester provides a raw TCP or UDP connection for testing "
            "connectivity between your laptop and industrial devices. It supports "
            "both client mode (connect to a device) and server mode (listen for "
            "incoming connections).\n\n"
            "This is useful for testing firewall rules, verifying that a device "
            "is accepting connections on a specific port, or debugging custom "
            "protocol communication. Data can be sent and viewed in both ASCII "
            "and hexadecimal format."
        ),
        "steps": [
            "Select Client or Server mode.",
            "Select TCP or UDP protocol.",
            "For Client mode: enter the target IP and port, then click Connect.",
            "For Server mode: enter the port to listen on (leave bind address as "
            "0.0.0.0 to accept connections on all adapters), then click Start.",
            "Type a message in the send bar and press Enter or click Send.",
            "Toggle between ASCII and Hex input format as needed.",
            "The message log shows all sent (green) and received (blue) data "
            "with timestamps and hex/ASCII representations.",
        ],
    },
    {
        "icon": "📋",
        "title": "BOOTP Configuration Tool",
        "description": (
            "The BOOTP Configuration Tool listens for BOOTP requests from "
            "unconfigured devices — such as Allen-Bradley modules that are in BOOTP "
            "mode — and allows you to assign IP addresses to them. This replicates "
            "the functionality of Rockwell's standalone BOOTP/DHCP Server utility.\n\n"
            "When an Allen-Bradley module powers up without a saved IP (or has been "
            "reset to factory defaults), it broadcasts BOOTP requests. This tool "
            "catches those requests and lets you configure the device's IP address, "
            "subnet mask, and gateway without needing Rockwell's separate utility."
        ),
        "steps": [
            "Connect your laptop directly to the device or to the same switch.",
            "Run the application as Administrator (required for port 67).",
            "Click 'Start Listening' to begin detecting BOOTP requests.",
            "When an unconfigured device is detected, it appears as a card "
            "showing the device's MAC address and vendor information.",
            "Enter the desired IP address, subnet mask, and gateway.",
            "Click 'Assign' — the tool sends a BOOTP reply with the configuration.",
            "The device receives the IP on its next BOOTP request cycle.",
        ],
    },
    {
        "icon": "🌐",
        "title": "DHCP Server",
        "description": (
            "The DHCP Server turns your laptop into a lightweight DHCP server, "
            "automatically assigning IP addresses to devices that connect to the "
            "network. This is useful when working on isolated networks or benches "
            "where there is no infrastructure DHCP server.\n\n"
            "Configure an IP pool range, subnet mask, gateway, and lease time. "
            "Toggle the server on and off with the switch. The active lease table "
            "shows all devices that have received an IP assignment.\n\n"
            "WARNING: Only use this on isolated networks. Running a DHCP server "
            "on a production network with an existing DHCP server will cause "
            "IP conflicts."
        ),
        "steps": [
            "Configure the IP pool range (start and end addresses).",
            "Set the subnet mask, gateway, and DNS server (gateway and DNS "
            "are optional for most industrial use cases).",
            "Set the lease time in seconds (default 3600 = 1 hour).",
            "Run the application as Administrator (required for port 67).",
            "Toggle the ON/OFF switch to start the server.",
            "Connect devices — they will automatically receive IPs from the pool.",
            "The Active Leases table shows all current assignments with MAC, "
            "IP, hostname, and remaining lease time.",
            "Toggle the switch OFF when done to stop the server.",
        ],
    },
    {
        "title": "Multi-Device Monitor",
        "icon": "📈",
        "description": (
            "The Multi-Device Monitor lets you track the health of multiple "
            "Ethernet devices simultaneously. Enter a list of IP addresses and "
            "the tool pings and sends CIP ListIdentity probes to each device at "
            "a configurable rate.\n\n"
            "A real-time trend chart shows response times "
            "for every device, color-coded so you can quickly spot degradation or "
            "dropouts. Below the chart, an analytics table displays per-device "
            "statistics: uptime percentage, min/avg/max ping, CIP response, "
            "outage count, and longest outage.\n\n"
            "When the session is complete, export a PDF report that includes the "
            "full-session trend chart and all device analytics. You can also "
            "export raw data as CSV for further analysis."
        ),
        "steps": [
            "Enter device IP addresses separated by commas or spaces in the "
            "Device IPs field.",
            "Set the poll rate (how often to probe each device). 1 second is a "
            "good default. Use 500ms for high-resolution monitoring.",
            "Set the timeout in milliseconds (default 2000ms).",
            "Click 'Start Monitor' to begin. The trend chart will start "
            "plotting response times immediately.",
            "Watch the trend chart for response time spikes or gaps (gaps = "
            "device didn't respond). The analytics table below updates live.",
            "Click 'Stop Monitor' when done.",
            "Click 'Export Report' for a branded PDF report including the "
            "full-session trend chart and per-device analytics table.",
            "Click 'Export CSV' to save raw timing data for spreadsheet analysis.",
        ],
    },
    {
        "title": "MAC Address Lookup",
        "icon": "🏷",
        "description": (
            "The MAC Address Lookup tool identifies the manufacturer of any "
            "network device from its MAC address. Enter one or more MAC addresses "
            "and the tool checks the built-in local database first, then searches "
            "the IEEE OUI registry online for any addresses not found locally.\n\n"
            "The local database contains vendor entries for the most common "
            "industrial automation, networking, and computing manufacturers — "
            "so most lookups are instant with no internet required.\n\n"
            "This is useful when you discover unknown devices on the network "
            "during a scan and need to quickly identify what they are. MAC "
            "addresses can be entered in any common format: "
            "AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABB.CCDD.EEFF, or raw hex."
        ),
        "steps": [
            "Navigate to the MAC Lookup page from the sidebar.",
            "Enter one or more MAC addresses separated by commas or spaces.",
            "Click 'Lookup' (or press Enter). The tool checks the local database "
            "first — most industrial vendors will be resolved instantly.",
            "For unknown MACs, the tool automatically queries the IEEE OUI "
            "registry online (internet required).",
            "Results show the vendor name, category (Automation / Networking / "
            "Computing / Other), OUI prefix, and whether the result came from "
            "the local database or online lookup.",
            "Click 'Clear' to reset results and start a new lookup session.",
        ],
    },
    {
        "title": "Packet Capture & Analysis",
        "icon": "🦈",
        "description": (
            "The Packet Capture tool is a Wireshark-style traffic analyzer built "
            "for people who don't know Wireshark. It captures live network traffic "
            "on the selected adapter for a configurable duration, then automatically "
            "analyzes the captured packets and presents findings in plain English — "
            "you never see a single raw packet.\n\n"
            "This is the tool to use when you suspect network-level problems like "
            "broadcast storms, IP address conflicts, excessive retransmissions, "
            "network loops, or bandwidth hogs. These are the kinds of issues that "
            "make PLCs lose communication intermittently but are invisible to "
            "standard ping tests.\n\n"
            "The analyzer automatically detects: broadcast storms and excessive "
            "broadcast traffic, TCP retransmissions (packet loss indicator), "
            "multicast flooding (common EIP/CIP issue), bandwidth hogs (single "
            "device consuming excessive bandwidth), protocol distribution, and "
            "non-industrial traffic on the control network.\n\n"
            "Results include a network health score, protocol breakdown donut chart, "
            "top talkers bar chart, event timeline, and detailed findings cards with "
            "specific troubleshooting recommendations.\n\n"
            "NOTE: Run this application as Administrator for best results. "
            "Administrator privileges allow promiscuous mode which captures ALL "
            "traffic on the network segment, not just the PC's own traffic."
        ),
        "steps": [
            "Right-click the application and select 'Run as administrator' for "
            "full promiscuous capture (recommended).",
            "Select the network interface to capture on. Choose the Ethernet adapter "
            "connected to the industrial network you want to analyze.",
            "Set the capture duration. 30 seconds is a good default. For catching "
            "intermittent issues, use 60-120 seconds. For broadcast storm detection, "
            "15 seconds is usually sufficient.",
            "Click 'Start Capture' to begin. The tool captures packets in the "
            "background with promiscuous mode to see all traffic on the segment.",
            "Wait for the capture to complete (or click Stop to end early). A progress "
            "bar shows elapsed time and remaining duration.",
            "When the capture completes, the tool automatically analyzes all captured "
            "packets and displays results.",
            "Check the Network Health score (0-100) for an at-a-glance assessment.",
            "Review the Protocol Breakdown chart to see what types of traffic are "
            "on the network. On a healthy industrial network, you should see mostly "
            "CIP/ENIP, ARP, and TCP.",
            "Check the Top Talkers chart to see which devices are using the most "
            "bandwidth. A single device dominating bandwidth may indicate a problem.",
            "Review the Timeline for discrete events like broadcast bursts, ARP "
            "conflicts, or spanning tree topology changes.",
            "Read through the Findings cards for detailed explanations and specific "
            "troubleshooting steps for any detected issues.",
            "Click 'Export Report' to save a text report of all findings for "
            "documentation or sharing with colleagues.",
        ],
    },
]


class HelpView(ctk.CTkFrame):
    """Help page — detailed tool descriptions and step-by-step guides."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._build_ui()

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BG_MEDIUM,
            scrollbar_button_hover_color=SAS_BLUE)
        scroll.pack(fill="both", expand=True)
        enable_touch_scroll(scroll)

        inner = scroll

        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(inner, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            hdr, text="📖  Help & User Guide",
            font=(FONT_FAMILY, FONT_SIZE_HEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            inner,
            text=f"{APP_FULL_NAME} v{APP_VERSION}  ·  {APP_COMPANY}",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=24, pady=(0, 4))

        ctk.CTkLabel(
            inner,
            text="This guide covers every tool in the application with detailed "
                 "descriptions and step-by-step instructions.",
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=24, pady=(0, 20))

        # ── Quick Reference ───────────────────────────────────────────────
        qr_card = ctk.CTkFrame(inner, fg_color=BG_CARD, corner_radius=8)
        qr_card.pack(fill="x", padx=24, pady=(0, 20))

        ctk.CTkLabel(
            qr_card, text="Quick Reference — Which Tool Should I Use?",
            font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 8))

        scenarios = [
            ("I'm on the right subnet and want to see what's on the network",
             "🔍  Network Scanner"),
            ("I plugged into an unknown network and need to find devices",
             "📡  Device Finder"),
            ("A device drops offline intermittently and I need to catch it",
             "📊  Ethernet Device Monitor"),
            ("I need to check if specific ports are open on a device",
             "🔎  Port Scanner"),
            ("I need to test raw TCP or UDP connectivity to a device",
             "🔌  Socket Tester"),
            ("I have an AB module stuck in BOOTP mode and need to assign an IP",
             "📋  BOOTP Config"),
            ("I'm on a bench with no DHCP server and need devices to get IPs",
             "🌐  DHCP Server"),
            ("I suspect broadcast storms, IP conflicts, or other traffic problems",
             "🦈  Packet Capture"),
        ]

        for scenario, tool in scenarios:
            row = ctk.CTkFrame(qr_card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)

            ctk.CTkLabel(
                row, text="→",
                font=(FONT_FAMILY, FONT_SIZE_BODY),
                text_color=SAS_ORANGE, anchor="w", width=20,
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=scenario,
                font=(FONT_FAMILY, FONT_SIZE_BODY),
                text_color=TEXT_SECONDARY, anchor="w",
            ).pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                row, text=tool,
                font=(FONT_FAMILY, FONT_SIZE_BODY, "bold"),
                text_color=SAS_BLUE_LIGHT, anchor="e",
            ).pack(side="right")

        ctk.CTkFrame(qr_card, fg_color="transparent", height=10).pack()

        # ── Tool Sections ─────────────────────────────────────────────────
        for section in HELP_SECTIONS:
            self._build_tool_section(inner, section)

        # ── Tips Section ──────────────────────────────────────────────────
        tips_card = ctk.CTkFrame(inner, fg_color=BG_CARD, corner_radius=8)
        tips_card.pack(fill="x", padx=24, pady=(4, 20))

        ctk.CTkLabel(
            tips_card, text="💡  General Tips",
            font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 8))

        tips = [
            "Run as Administrator — Some network operations (ARP probing, raw "
            "sockets) work better with elevated privileges. Right-click the app "
            "and select 'Run as administrator' for best results.",
            "Disable Windows Firewall temporarily if device discovery seems to "
            "miss devices. Windows Firewall can block ICMP and UDP broadcasts.",
            "Use a USB Ethernet adapter for isolation. Your laptop's built-in "
            "NIC can stay connected to your corporate network while the USB "
            "adapter connects to the industrial network.",
            "Set your adapter to DHCP before using Device Finder. This ensures "
            "you get a link-local address (169.254.x.x) which still allows "
            "ARP-level discovery across subnets.",
            "Export CSV after every monitoring session for documentation. The "
            "raw data can be analyzed further in Excel or shared with the "
            "customer.",
            "Hide unused adapters in Settings to keep the adapter dropdowns "
            "clean. VMware, VPN, and Hyper-V adapters just add clutter.",
        ]

        for tip in tips:
            tip_row = ctk.CTkFrame(tips_card, fg_color="transparent")
            tip_row.pack(fill="x", padx=16, pady=3)

            ctk.CTkLabel(
                tip_row, text="•",
                font=(FONT_FAMILY, FONT_SIZE_BODY),
                text_color=SAS_ORANGE, anchor="nw", width=16,
            ).pack(side="left", anchor="n", pady=(2, 0))

            ctk.CTkLabel(
                tip_row, text=tip,
                font=(FONT_FAMILY, FONT_SIZE_BODY),
                text_color=TEXT_SECONDARY, anchor="w",
                wraplength=700, justify="left",
            ).pack(side="left", fill="x", expand=True)

        ctk.CTkFrame(tips_card, fg_color="transparent", height=10).pack()

        # Bottom spacer
        ctk.CTkFrame(inner, fg_color="transparent", height=20).pack()

    def _build_tool_section(self, parent, section: dict):
        """Build a single tool help section with description and steps."""
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        card.pack(fill="x", padx=24, pady=(0, 12))

        # Tool title
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            title_row, text=f"{section['icon']}  {section['title']}",
            font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(side="left")

        # Description label
        ctk.CTkLabel(
            card, text="OVERVIEW",
            font=(FONT_FAMILY, FONT_SIZE_TINY, "bold"),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=16, pady=(8, 2))

        ctk.CTkLabel(
            card, text=section["description"],
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            text_color=TEXT_SECONDARY, anchor="w",
            wraplength=720, justify="left",
        ).pack(fill="x", padx=16, pady=(0, 8))

        # Divider
        ctk.CTkFrame(card, fg_color=BORDER_COLOR, height=1).pack(
            fill="x", padx=16, pady=4)

        # Step-by-step
        ctk.CTkLabel(
            card, text="STEP-BY-STEP",
            font=(FONT_FAMILY, FONT_SIZE_TINY, "bold"),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=16, pady=(8, 4))

        for i, step in enumerate(section["steps"], 1):
            step_row = ctk.CTkFrame(card, fg_color="transparent")
            step_row.pack(fill="x", padx=16, pady=2)

            # Step number badge
            badge = ctk.CTkFrame(
                step_row, fg_color=SAS_BLUE, corner_radius=10,
                width=22, height=22)
            badge.pack(side="left", anchor="n", padx=(0, 8), pady=(2, 0))
            badge.pack_propagate(False)

            ctk.CTkLabel(
                badge, text=str(i),
                font=(FONT_FAMILY, FONT_SIZE_TINY, "bold"),
                text_color="white",
            ).place(relx=0.5, rely=0.5, anchor="center")

            # Step text
            ctk.CTkLabel(
                step_row, text=step,
                font=(FONT_FAMILY, FONT_SIZE_BODY),
                text_color=TEXT_SECONDARY, anchor="w",
                wraplength=680, justify="left",
            ).pack(side="left", fill="x", expand=True)

        # Bottom padding
        ctk.CTkFrame(card, fg_color="transparent", height=10).pack()
