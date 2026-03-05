# SAS Network Diagnostic Tool

**Industrial Ethernet Diagnostic Suite for Automation Professionals**

Developed by [Southern Automation Solutions](https://www.sascontrols.com) · Valdosta, GA

---

## Overview

The SAS Network Diagnostic Tool is a comprehensive Windows desktop application purpose-built for industrial automation environments. It combines network discovery, real-time device monitoring, traffic analysis, and link quality testing into a single unified interface — and translates complex technical data into plain-language diagnostics that any automation professional can act on.

Designed for Allen-Bradley, Siemens, Yaskawa, and other industrial Ethernet device ecosystems, the tool is built to handle the demands of factory-floor network troubleshooting without requiring deep networking expertise.

---

## Features at a Glance

| Module | What It Does |
|---|---|
| **Network Scanner** | ICMP sweep + ARP harvest + EtherNet/IP identity pull. Discovers every device on the subnet, identifies vendors, open ports, and product info. Exports branded PDF report. |
| **Device Monitor** | Continuous Ping / TCP / CIP polling of a single device. Tracks response time trends, detects outages, and runs automated diagnostic analysis with plain-language findings and recommendations. |
| **Multi-Device Monitor** | Simultaneous monitoring of up to 16+ devices on a single live trend chart. Per-device color coding, solo/isolation view, stacked chart mode, and full diagnostic analysis with per-device findings. |
| **Packet Capture & Analysis** | Live or file-based packet capture with automated detection of TCP retransmissions, ARP storms, duplicate IPs, STP topology changes, bandwidth hogs, and more. Health score + branded PDF report. |
| **Link Quality Analyzer** | Tests a target device with escalating frame sizes to detect MTU limits, duplex mismatches, and burst-load sensitivity. Calculates jitter, packet loss, and produces a scored health report. |
| **BOOTP Configuration Tool** | Listens for BOOTP requests from unconfigured devices and assigns IP addresses. Useful for commissioning Allen-Bradley PLCs, drives, and other devices that use BOOTP for initial IP assignment. |
| **Device Finder** | Discovers devices on factory-default subnets (Allen-Bradley, Siemens, Schneider, Beckhoff, WAGO, etc.) even when the laptop is on a different subnet. |
| **Port Scanner** | Fast targeted port scanner with industrial protocol presets (EtherNet/IP, Modbus, Profinet, HTTP, SSH, SNMP, etc.). |
| **MAC Address Lookup** | Resolves MAC addresses to manufacturer names using a curated offline OUI database covering major industrial vendors, with optional online fallback. |
| **DHCP Server** | Lightweight configurable DHCP server for temporarily handing out IPs on isolated network segments. |
| **TCP/UDP Socket Tester** | Raw socket connection tester for verifying that specific TCP/UDP ports are open and responsive. |

---

## Report Generation

All primary diagnostic modules generate **branded PDF reports** suitable for sharing with customers or keeping on file:

- Network Scan Report — Device inventory (without Type column), EIP device details with MAC addresses, open ports, and ping times
- Device Monitor Report — Full session statistics, health score, detailed findings with root-cause explanation and resolution steps, outage log
- Multi-Device Monitor Report — Trend chart, per-device analytics table, and full per-device diagnostic findings
- Packet Capture Report — Protocol breakdown, top talkers, detailed findings with expanded data tables (TCP retransmission sources, ARP sources, conflict table)
- Link Quality Report — RTT vs payload size chart, burst test results, health score banner, and diagnostic findings

---

## Screenshots

> *Screenshots pending — production UI with real network data.*

| Network Scanner | Device Monitor | Multi-Device Trend |
|---|---|---|
| *(screenshot)* | *(screenshot)* | *(screenshot)* |

| Packet Capture Analysis | Link Quality Analyzer | BOOTP Tool |
|---|---|---|
| *(screenshot)* | *(screenshot)* | *(screenshot)* |

---

## System Requirements

| Requirement | Minimum |
|---|---|
| **OS** | Windows 10 / 11 (64-bit) |
| **Python** | 3.10+ |
| **Network** | Ethernet adapter connected to the target network |
| **Privileges** | Administrator required for Packet Capture, BOOTP, and DHCP features |

### Python Dependencies

```
customtkinter >= 5.2.0
pycomm3 >= 1.2.0
Pillow >= 10.0.0
psutil >= 5.9.0
reportlab >= 4.0.0
```

Optional for Packet Capture:
- [Npcap](https://npcap.com/) (Windows packet capture driver)
- `scapy` Python package

Install all dependencies:
```bash
pip install -r requirements.txt
```

---

## Running the Application

```bash
python main.py
```

> The application requires **Run as Administrator** for packet capture, BOOTP server, and DHCP server features. Right-click `main.py` or your shortcut and choose "Run as administrator."

---

## Building a Standalone Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "SAS-NetDiag" main.py
```

The compiled `.exe` will be in the `dist/` folder and can be distributed without requiring Python to be installed on the target machine.

---

## MAC Vendor Database

The tool uses a curated offline OUI database (`core/mac_vendors.py`) covering major industrial automation vendors:

- Rockwell Automation / Allen-Bradley (13 OUIs)
- Siemens AG (21 OUIs)
- Yaskawa Electric Corporation (`00:20:B5`)
- Banner Engineering (`00:23:D9`)
- Beckhoff, WAGO, Moxa, Phoenix Contact, Pepperl+Fuchs, ProSoft, and many more

An optional online lookup fallback queries public MAC APIs when a vendor is not found in the offline database.

---

## Architecture

```
SAS-NetDiag/
├── main.py                     # Application entry point
├── requirements.txt
├── Source Code/
│   ├── core/                   # Engine modules
│   │   ├── device_discovery.py     # ICMP/ARP/EIP scanning
│   │   ├── eip_scanner.py          # EtherNet/IP identity queries
│   │   ├── monitor_engine.py       # Single-device polling engine
│   │   ├── multi_monitor.py        # Multi-device polling engine
│   │   ├── monitor_analyzer.py     # Diagnostic analysis engine
│   │   ├── capture_engine.py       # Packet capture (Scapy)
│   │   ├── capture_analyzer.py     # Traffic analysis engine
│   │   ├── link_quality.py         # Link quality test engine
│   │   ├── mac_vendors.py          # Offline OUI database
│   │   ├── pdf_report.py           # PDF report generator (ReportLab)
│   │   ├── bootp_server.py         # BOOTP server
│   │   ├── dhcp_server.py          # DHCP server
│   │   └── port_scanner.py         # TCP port scanner
│   └── ui/                     # CustomTkinter UI modules
│       ├── scan_view.py            # Network Scanner page
│       ├── monitor_view.py         # Device Monitor page
│       ├── multi_monitor_view.py   # Multi-Device Monitor page
│       ├── capture_view.py         # Packet Capture page
│       ├── link_quality_view.py    # Link Quality Analyzer page
│       ├── bootp_view.py           # BOOTP Tool page
│       ├── finder_view.py          # Device Finder page
│       ├── port_scanner_view.py    # Port Scanner page
│       ├── mac_lookup_view.py      # MAC Lookup page
│       ├── dhcp_view.py            # DHCP Server page
│       ├── socket_tester_view.py   # Socket Tester page
│       ├── widgets.py              # Shared UI components
│       └── theme.py                # Color/font constants
```

---

## Key Design Principles

- **Plain-language diagnostics** — every finding includes what was observed, what it means in an industrial context, and what to do about it
- **No networking expertise required** — the tool is designed for automation professionals, not network engineers
- **Offline-first** — the OUI vendor database and all core analysis runs completely offline; internet is optional
- **Industrial context-aware** — findings are explained in terms of PLC I/O faults, HMI freezes, MSG instruction timeouts, and VFD communication loss — not generic IT terminology

---

## License

Proprietary — Southern Automation Solutions. Not licensed for redistribution.

---

## Contact

**Southern Automation Solutions**  
111 Hemlock St. Suite A, Valdosta, GA 31601  
📞 229-563-2897  
📧 Contact@SASControls.com  
🌐 www.SASControls.com
