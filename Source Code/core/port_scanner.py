"""
SAS Network Diagnostic Tool — Port Scanner Engine
Concurrent port scanning with service identification for industrial networks.
"""

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Callable, Dict, Tuple

logger = logging.getLogger(__name__)


# ── Well-Known Service Identification ────────────────────────────────────────

SERVICE_MAP: Dict[int, str] = {
    20: "FTP Data",
    21: "FTP Control",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    102: "Siemens S7 / ISO-TSAP",
    110: "POP3",
    135: "MS RPC / DCOM",
    137: "NetBIOS Name",
    138: "NetBIOS Datagram",
    139: "NetBIOS Session",
    143: "IMAP",
    161: "SNMP",
    162: "SNMP Trap",
    443: "HTTPS",
    445: "SMB / CIFS",
    502: "Modbus TCP",
    503: "Modbus TCP (alt)",
    993: "IMAPS",
    995: "POP3S",
    1433: "MS SQL Server",
    1434: "MS SQL Monitor",
    1883: "MQTT",
    2049: "NFS",
    2222: "EtherNet/IP (explicit)",
    3306: "MySQL",
    3389: "RDP",
    4840: "OPC UA",
    4843: "OPC UA (TLS)",
    5432: "PostgreSQL",
    5900: "VNC",
    8443: "HTTPS Alt",
    8883: "MQTT (TLS)",
    9100: "Raw Printing",
    18245: "GE SRTP",
    20000: "DNP3",
    28784: "Kepware OPC",
    44818: "EtherNet/IP (IO)",
    47808: "BACnet",
    48898: "Beckhoff ADS",
}

# Common industrial port presets
PRESET_COMMON = [21, 22, 23, 80, 102, 135, 443, 445, 502, 2222, 3389, 4840, 44818, 47808]
PRESET_ALLEN_BRADLEY = [80, 443, 2222, 44818]
PRESET_SIEMENS = [80, 102, 443, 4840]
PRESET_MODBUS = [502, 503, 80, 443]
PRESET_WEB = [80, 443, 8080, 8443]
PRESET_ALL_COMMON = sorted(set(SERVICE_MAP.keys()))


@dataclass
class PortResult:
    """Result of scanning a single port."""
    port: int
    status: str = ""     # "open", "closed", "filtered"
    service: str = ""    # Identified service name
    banner: str = ""     # Banner grab result
    response_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScanResult:
    """Complete port scan result for a target."""
    target: str
    ports_scanned: int = 0
    open_ports: List[PortResult] = field(default_factory=list)
    closed_ports: List[PortResult] = field(default_factory=list)
    filtered_ports: List[PortResult] = field(default_factory=list)
    scan_start: Optional[datetime] = None
    scan_end: Optional[datetime] = None
    error: str = ""

    @property
    def duration_seconds(self) -> float:
        if self.scan_start and self.scan_end:
            return (self.scan_end - self.scan_start).total_seconds()
        return 0.0

    @property
    def all_results(self) -> List[PortResult]:
        return sorted(
            self.open_ports + self.closed_ports + self.filtered_ports,
            key=lambda r: r.port,
        )


class PortScannerEngine:
    """
    Concurrent port scanner with service identification.

    Callbacks:
      on_port_result(PortResult) — each port as it completes
      on_progress(scanned, total) — progress update
      on_complete(ScanResult) — scan finished
    """

    def __init__(self):
        self._scanning = False
        self._cancel = False
        self._thread: Optional[threading.Thread] = None

        self.on_port_result: Optional[Callable[[PortResult], None]] = None
        self.on_progress: Optional[Callable[[int, int], None]] = None
        self.on_complete: Optional[Callable[[ScanResult], None]] = None

    @property
    def is_scanning(self) -> bool:
        return self._scanning

    def scan(self, target: str, ports: List[int],
             timeout: float = 1.0, max_threads: int = 50,
             grab_banner: bool = True):
        """Start a port scan against a target host."""
        if self._scanning:
            return

        self._scanning = True
        self._cancel = False

        def _run():
            result = ScanResult(target=target, ports_scanned=len(ports))
            result.scan_start = datetime.now()
            scanned = 0

            try:
                # Resolve hostname first
                try:
                    socket.getaddrinfo(target, None)
                except socket.gaierror as e:
                    result.error = f"Cannot resolve host: {target} ({e})"
                    result.scan_end = datetime.now()
                    self._emit_complete(result)
                    self._scanning = False
                    return

                with ThreadPoolExecutor(max_workers=max_threads) as executor:
                    futures = {
                        executor.submit(
                            self._scan_port, target, port, timeout, grab_banner
                        ): port
                        for port in ports
                    }

                    for future in as_completed(futures):
                        if self._cancel:
                            break

                        port_result = future.result()
                        if port_result.status == "open":
                            result.open_ports.append(port_result)
                        elif port_result.status == "closed":
                            result.closed_ports.append(port_result)
                        else:
                            result.filtered_ports.append(port_result)

                        scanned += 1
                        self._emit_port_result(port_result)
                        self._emit_progress(scanned, len(ports))

            except Exception as e:
                result.error = str(e)
                logger.error(f"Port scan error: {e}", exc_info=True)

            result.scan_end = datetime.now()
            self._scanning = False
            self._emit_complete(result)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def cancel(self):
        """Cancel the current scan."""
        self._cancel = True

    def _scan_port(self, target: str, port: int,
                   timeout: float, grab_banner: bool) -> PortResult:
        """Scan a single port."""
        result = PortResult(port=port, service=SERVICE_MAP.get(port, ""))

        start = time.perf_counter()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            err = sock.connect_ex((target, port))
            elapsed = (time.perf_counter() - start) * 1000
            result.response_ms = round(elapsed, 1)

            if err == 0:
                result.status = "open"

                # Try banner grab
                if grab_banner:
                    try:
                        sock.settimeout(0.5)
                        # Send HTTP probe for web ports
                        if port in (80, 443, 8080, 8443):
                            sock.send(b"HEAD / HTTP/1.0\r\n\r\n")
                        data = sock.recv(256)
                        if data:
                            result.banner = data.decode("utf-8", errors="replace").strip()[:128]
                    except Exception:
                        pass
            else:
                result.status = "closed"

            sock.close()

        except socket.timeout:
            result.status = "filtered"
            result.response_ms = timeout * 1000
        except OSError as e:
            # Connection refused = closed, other errors = filtered
            if e.errno in (111, 10061):  # ECONNREFUSED
                result.status = "closed"
            else:
                result.status = "filtered"

        return result

    @staticmethod
    def parse_port_input(text: str) -> List[int]:
        """
        Parse user port input. Supports:
          - Single ports: "80"
          - Comma-separated: "80, 443, 502"
          - Ranges: "1-1024"
          - Mixed: "22, 80, 100-200, 443, 44818"
        """
        ports = set()
        text = text.strip()
        if not text:
            return []

        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    start, end = int(start.strip()), int(end.strip())
                    if 1 <= start <= 65535 and 1 <= end <= 65535:
                        ports.update(range(start, end + 1))
                except ValueError:
                    continue
            else:
                try:
                    p = int(part)
                    if 1 <= p <= 65535:
                        ports.add(p)
                except ValueError:
                    continue

        return sorted(ports)

    def _emit_port_result(self, result: PortResult):
        if self.on_port_result:
            try:
                self.on_port_result(result)
            except Exception:
                pass

    def _emit_progress(self, scanned: int, total: int):
        if self.on_progress:
            try:
                self.on_progress(scanned, total)
            except Exception:
                pass

    def _emit_complete(self, result: ScanResult):
        if self.on_complete:
            try:
                self.on_complete(result)
            except Exception:
                pass
