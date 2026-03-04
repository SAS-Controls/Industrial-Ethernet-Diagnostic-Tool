# SAS Network Diagnostic Tool v3.1.0

**Comprehensive Ethernet network diagnostics for industrial automation.**

All-in-one tool for discovering, monitoring, and troubleshooting Ethernet
networks in industrial environments. Designed for automation technicians
who need reliable network diagnostics without specialized training.

---

## Tools

### Diagnostics
- **Network Scanner** — Ping sweep, ARP harvest, EtherNet/IP broadcast discovery
- **Device Finder** — Cross-subnet device discovery via EIP, BOOTP, mDNS, Profinet DCP
- **Device Monitor** — Continuous ping + CIP polling with pattern analysis, export PDF report
- **Multi-Device Monitor** — Monitor multiple IPs simultaneously with real-time trend chart, per-device analytics, CSV/PDF export
- **Packet Capture** — Wireshark-style capture with automated plain-language analysis

### Utilities
- **Port Scanner** — Concurrent TCP port scanning with industrial service identification and presets
- **Socket Tester** — Raw TCP/UDP client/server for connectivity testing
- **BOOTP Config** — Assign IPs to unconfigured devices (replaces Rockwell BOOTP utility)
- **DHCP Server** — Lightweight DHCP server for isolated bench/field networks
- **MAC Lookup** — Identify device manufacturers from MAC address (local DB + online IEEE lookup)

## New in v3.1.0

- **Multi-Device Monitor** with real-time trend chart, analytics table, and PDF/CSV export
- **MAC Address Lookup** page with local database + automatic IEEE online fallback
- **Device Diagnostic Export** — PDF report from single-device diagnostics
- **Port Scanner fix** — Resolved PortResult initialization error
- **APP_PHASE crash fix** — Resolved settings_view crash from removed constant
- Trend chart uses pure tkinter Canvas — no extra dependencies required

## Quick Start

1. Copy SAS-NetDiag.exe to any Windows 10/11 PC
2. Double-click to run — no installation needed
3. Select your network adapter and start scanning

## Building

    pip install -r requirements.txt
    build.bat

Output: dist\SAS-NetDiag.exe

---

*Southern Automation Solutions — 111 Hemlock St. Ste A, Valdosta, GA 31601*
