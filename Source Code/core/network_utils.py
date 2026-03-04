"""
SAS Network Diagnostics Tool — Network Utilities
Low-level network operations: interface detection, ping sweep, ARP lookups.
Uses only standard library + psutil to avoid WinPcap/Npcap dependency.
"""

import ipaddress
import logging
import platform
import re
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)


@dataclass
class NetworkInterface:
    """Represents a local network interface."""
    name: str
    display_name: str
    ip_address: str
    subnet_mask: str
    mac_address: str
    is_up: bool = True
    speed_mbps: int = 0

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(f"{self.ip_address}/{self.subnet_mask}", strict=False)

    @property
    def host_count(self) -> int:
        return self.network.num_addresses - 2  # Exclude network and broadcast

    def __str__(self):
        return f"{self.display_name} ({self.ip_address}/{self.subnet_mask})"


@dataclass
class DiscoveredDevice:
    """A device found on the network."""
    ip_address: str
    mac_address: str = ""
    hostname: str = ""
    vendor: str = ""
    is_reachable: bool = True
    response_time_ms: float = 0.0
    open_ports: List[int] = field(default_factory=list)
    device_type: str = "Unknown"
    product_name: str = ""
    serial_number: str = ""
    firmware_rev: str = ""
    eip_identity: Optional[dict] = None
    last_seen: float = field(default_factory=time.time)

    @property
    def display_name(self) -> str:
        if self.product_name:
            return self.product_name
        if self.hostname and self.hostname != self.ip_address:
            return self.hostname
        if self.vendor:
            return f"{self.vendor} Device"
        if self.device_type and self.device_type != "Unknown":
            return f"{self.device_type}"
        return self.ip_address


def get_network_interfaces() -> List[NetworkInterface]:
    """Detect all active network interfaces with IPv4 addresses."""
    interfaces = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for name, addr_list in addrs.items():
        stat = stats.get(name)
        if not stat or not stat.isup:
            continue

        for addr in addr_list:
            if addr.family == socket.AF_INET and addr.address != "127.0.0.1":
                # Get MAC address from the same interface
                mac = ""
                for a in addr_list:
                    if a.family == psutil.AF_LINK:
                        mac = a.address
                        break

                iface = NetworkInterface(
                    name=name,
                    display_name=name,
                    ip_address=addr.address,
                    subnet_mask=addr.netmask or "255.255.255.0",
                    mac_address=mac,
                    is_up=stat.isup,
                    speed_mbps=stat.speed if stat.speed else 0,
                )
                interfaces.append(iface)
                logger.info(f"Found interface: {iface}")

    return interfaces


def ping_host(ip: str, timeout: float = 1.0,
              source_ip: str = "") -> Tuple[bool, float]:
    """
    Ping a single host and return (reachable, response_time_ms).
    Uses system ping command for compatibility without raw sockets.

    Args:
        ip: Target IP to ping
        timeout: Timeout in seconds
        source_ip: Source IP to bind to (forces ping through specific adapter).
                   If empty, OS chooses the route automatically.
    """
    try:
        is_win = platform.system().lower() == "windows"
        cmd = ["ping"]

        if is_win:
            cmd += ["-n", "1", "-w", str(int(timeout * 1000))]
            # -S forces ping through the adapter that owns this IP
            if source_ip:
                cmd += ["-S", source_ip]
        else:
            cmd += ["-c", "1", "-W", str(int(timeout))]
            # -I forces ping through specific interface/IP
            if source_ip:
                cmd += ["-I", source_ip]

        cmd.append(ip)

        start = time.perf_counter()
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 2,
            creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0,
        )
        elapsed = (time.perf_counter() - start) * 1000

        if result.returncode == 0:
            match = re.search(r"time[=<](\d+\.?\d*)", result.stdout)
            if match:
                elapsed = float(match.group(1))
            return True, round(elapsed, 2)
        return False, 0.0

    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Ping failed for {ip}: {e}")
        return False, 0.0


def get_arp_table(interface_ip: str = "") -> Dict[str, str]:
    """
    Read the system ARP table and return a dict of {ip: mac}.

    Args:
        interface_ip: If provided, only return ARP entries from the
                      interface that owns this IP address.  On Windows
                      this uses 'arp -a -N <ip>' which is critical for
                      avoiding cross-interface leakage (e.g. WiFi entries
                      appearing when scanning Ethernet).
    """
    ip_mac_map = {}
    is_win = platform.system().lower() == "windows"
    flags = subprocess.CREATE_NO_WINDOW if is_win else 0

    try:
        cmd = ["arp", "-a"]
        if is_win and interface_ip:
            cmd += ["-N", interface_ip]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            creationflags=flags,
        )
        for line in result.stdout.splitlines():
            if is_win:
                match = re.search(
                    r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F]{2}[-:][\da-fA-F]{2}[-:][\da-fA-F]{2}[-:]"
                    r"[\da-fA-F]{2}[-:][\da-fA-F]{2}[-:][\da-fA-F]{2})",
                    line,
                )
            else:
                match = re.search(
                    r"\((\d+\.\d+\.\d+\.\d+)\) at ([\da-fA-F]{2}:[\da-fA-F]{2}:[\da-fA-F]{2}:"
                    r"[\da-fA-F]{2}:[\da-fA-F]{2}:[\da-fA-F]{2})",
                    line,
                )
            if match:
                ip = match.group(1)
                mac = match.group(2).replace("-", ":").upper()
                if mac in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00"):
                    continue
                if mac.startswith("01:00:5E"):
                    continue
                try:
                    if ipaddress.IPv4Address(ip).is_multicast:
                        continue
                except Exception:
                    pass
                ip_mac_map[ip] = mac

    except Exception as e:
        logger.warning(f"Failed to read ARP table: {e}")

    return ip_mac_map


def resolve_hostname(ip: str, timeout: float = 1.0) -> str:
    """Attempt reverse DNS lookup for an IP address."""
    try:
        socket.setdefaulttimeout(timeout)
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout, OSError):
        return ""


def check_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a specific TCP port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# Common industrial Ethernet ports to check
INDUSTRIAL_PORTS = {
    80: "HTTP (Web Server)",
    443: "HTTPS",
    44818: "EtherNet/IP (CIP)",
    2222: "EtherNet/IP (Implicit I/O)",
    502: "Modbus TCP",
    102: "Siemens S7 / ISO-TSAP",
    4840: "OPC UA",
    20000: "DNP3",
    47808: "BACnet",
}


def scan_industrial_ports(ip: str, timeout: float = 0.5) -> List[int]:
    """Scan common industrial ports on a device — all ports in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    open_ports = []
    with ThreadPoolExecutor(max_workers=len(INDUSTRIAL_PORTS)) as ex:
        futs = {ex.submit(check_port, ip, port, timeout): port
                for port in INDUSTRIAL_PORTS}
        for fut in as_completed(futs):
            try:
                if fut.result():
                    open_ports.append(futs[fut])
            except Exception:
                pass
    return open_ports


def scan_ports_batch(
    devices: list,
    timeout: float = 0.15,
    max_workers: int = 120,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable] = None,
) -> None:
    """
    Scan industrial ports on ALL devices concurrently.

    Instead of scanning one device at a time (sequential = minutes),
    this fires off every (device, port) combination at once with a
    thread pool.  For 21 devices × 9 ports = 189 checks, all running
    in parallel, the total time equals ONE timeout (~0.15s) rather
    than 189 × 0.3s = 57s.

    Args:
        devices:     List of DiscoveredDevice objects to enrich
        timeout:     Socket connect timeout (0.15s is plenty for LAN)
        max_workers: Thread pool size
        cancel_event: Set to cancel early
        progress_callback: fn(done_count, total_count) for updates
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not devices:
        return

    # Build all (device, port) jobs
    jobs = []
    for dev in devices:
        for port in INDUSTRIAL_PORTS:
            jobs.append((dev, port))

    total = len(jobs)
    done = [0]
    results_lock = threading.Lock()

    def probe_one(device, port):
        if cancel_event and cancel_event.is_set():
            return
        is_open = check_port(device.ip_address, port, timeout)
        if is_open:
            with results_lock:
                device.open_ports.append(port)

    with ThreadPoolExecutor(max_workers=min(max_workers, total)) as ex:
        futs = []
        for dev, port in jobs:
            if cancel_event and cancel_event.is_set():
                break
            futs.append(ex.submit(probe_one, dev, port))

        for fut in as_completed(futs):
            if cancel_event and cancel_event.is_set():
                for f in futs:
                    f.cancel()
                break
            try:
                fut.result(timeout=timeout + 1)
            except Exception:
                pass
            done[0] += 1
            if progress_callback and done[0] % 20 == 0:
                progress_callback(done[0], total)


def identify_device_type(open_ports: List[int], mac: str = "", eip_data: dict = None) -> str:
    """
    Identify the device type/manufacturer based on all available information.

    Priority order:
    1. EtherNet/IP CIP identity data (most reliable for EIP devices)
    2. MAC address OUI vendor lookup (works for ALL devices)
    3. Open port heuristics (fallback)
    """
    from core.mac_vendors import lookup_vendor

    # 1) CIP identity — highest confidence
    if eip_data:
        vendor_id = eip_data.get("vendor_id", 0)
        if vendor_id == 1:
            return "Allen-Bradley (Rockwell)"
        elif vendor_id == 34:
            return "Turck"
        elif vendor_id == 43:
            return "WAGO"
        elif vendor_id == 44:
            return "Banner Engineering"
        elif vendor_id == 283:
            return "Molex"
        elif vendor_id == 90:
            return "HMS Industrial (Anybus)"
        elif vendor_id == 40:
            return "Siemens"
        elif vendor_id == 48:
            return "Phoenix Contact"
        elif vendor_id == 345:
            return "Beckhoff Automation"
        elif vendor_id == 50:
            return "Schneider Electric"

    # 2) MAC address vendor lookup — works for all devices with a MAC
    if mac:
        vendor_name, category = lookup_vendor(mac)
        if vendor_name != "Unknown":
            return vendor_name

    # 3) Open port heuristics — fallback when no MAC or unknown MAC
    if 44818 in open_ports:
        return "EtherNet/IP Device"
    if 502 in open_ports:
        return "Modbus TCP Device"
    if 102 in open_ports:
        return "Siemens S7 Device"
    if 4840 in open_ports:
        return "OPC UA Device"
    if 47808 in open_ports:
        return "BACnet Device"
    if 20000 in open_ports:
        return "DNP3 Device"
    if 80 in open_ports or 443 in open_ports:
        return "Network Device (Web)"

    return "Unknown"


def ping_sweep(network: ipaddress.IPv4Network,
               progress_callback: Optional[Callable[[int, int, str], None]] = None,
               cancel_event: Optional[threading.Event] = None,
               max_threads: int = 50,
               source_ip: str = "",
               explicit_hosts: Optional[List[str]] = None) -> List[DiscoveredDevice]:
    """
    Fast network sweep: TCP connect probes + ARP table harvest.

    Instead of spawning 254 separate ping.exe processes (~2-4 minutes),
    this uses lightweight TCP socket connects to trigger ARP exchanges
    and discover live hosts.  All 254 hosts are probed concurrently with
    very short timeouts (0.1s), then the ARP table is read to find every
    device that responded at Layer 2 — including devices that block ICMP.

    For devices that ARE found, we do a quick ICMP ping to get the RTT
    (just the ~20 live hosts, not all 254).

    If explicit_hosts is provided, those IPs are scanned instead of
    network.hosts().  This supports custom ranges like 10.0.0.5-10.0.0.20.

    Typical /24 scan: 3-8 seconds instead of 2-4 minutes.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if explicit_hosts:
        hosts = [ipaddress.IPv4Address(h) for h in explicit_hosts]
    else:
        hosts = list(network.hosts())
    total = len(hosts)

    if total > 1022:
        logger.warning(f"Subnet {network} has {total:,} hosts — capping to 254")
        hosts = hosts[:254]
        total = len(hosts)

    if total == 0:
        return []

    found_ips: Dict[str, float] = {}  # ip -> response_time_ms
    found_lock = threading.Lock()
    completed = [0]

    # ── Phase A: Fast TCP probe all hosts ─────────────────────────────
    # A TCP connect to ANY port triggers an ARP exchange on the local
    # segment.  Even if the port is closed (RST), the device's MAC will
    # appear in the ARP table.  We probe 3 common ports per host with
    # very short timeouts — we don't care about the port result, just
    # that the host is alive.
    PROBE_PORTS = [80, 44818, 502]  # HTTP, EtherNet/IP, Modbus

    def tcp_probe_host(ip_str):
        """Quick TCP probes to trigger ARP — doesn't matter if ports are open."""
        if cancel_event and cancel_event.is_set():
            return
        start = time.perf_counter()
        alive = False
        for port in PROBE_PORTS:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                if source_ip:
                    try:
                        sock.bind((source_ip, 0))
                    except OSError:
                        pass
                result = sock.connect_ex((ip_str, port))
                sock.close()
                if result == 0:  # Port actually open
                    alive = True
                    break
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
        elapsed = (time.perf_counter() - start) * 1000

        with found_lock:
            completed[0] += 1
            if progress_callback and completed[0] % 10 == 0:
                progress_callback(completed[0], total, ip_str)

        if alive:
            with found_lock:
                found_ips[ip_str] = round(elapsed, 2)

    logger.info(f"Fast TCP sweep: {total} hosts × {len(PROBE_PORTS)} ports...")
    with ThreadPoolExecutor(max_workers=min(150, total)) as ex:
        futs = []
        for host in hosts:
            if cancel_event and cancel_event.is_set():
                break
            futs.append(ex.submit(tcp_probe_host, str(host)))
        for fut in as_completed(futs):
            if cancel_event and cancel_event.is_set():
                for f in futs:
                    f.cancel()
                break
            try:
                fut.result(timeout=2)
            except Exception:
                pass

    if cancel_event and cancel_event.is_set():
        return []

    # ── Phase B: Harvest ARP table ────────────────────────────────────
    # The TCP probes triggered ARP exchanges for every live host.
    # Now read the ARP table to catch devices that didn't have open
    # probe ports but DID respond at Layer 2 (ARP).
    time.sleep(0.3)  # Let ARP table settle

    # Build the set of allowed IPs for filtering ARP results
    if explicit_hosts:
        allowed_host_set = set(explicit_hosts)
    else:
        allowed_host_set = None  # Use network membership check

    arp_table = get_arp_table(interface_ip=source_ip)
    for ip, mac in arp_table.items():
        try:
            if allowed_host_set is not None:
                # Explicit range: only include IPs in the list
                if ip not in allowed_host_set:
                    continue
            else:
                # CIDR/subnet mode: check network membership
                if ipaddress.IPv4Address(ip) not in network:
                    continue
        except Exception:
            continue
        if mac in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00"):
            continue
        if ip not in found_ips:
            found_ips[ip] = 0.0  # Found via ARP, no RTT yet

    logger.info(f"TCP sweep + ARP found {len(found_ips)} live hosts")

    if cancel_event and cancel_event.is_set():
        return []

    # ── Phase C: Quick ICMP ping only the live hosts ──────────────────
    # Now we only ping the ~20 devices we actually found (not all 254).
    # This gets us accurate RTT values for the report.
    def ping_live(ip_str):
        if cancel_event and cancel_event.is_set():
            return
        reachable, rtt = ping_host(ip_str, timeout=0.5, source_ip=source_ip)
        if reachable and rtt > 0:
            with found_lock:
                found_ips[ip_str] = rtt

    if found_ips:
        live_list = list(found_ips.keys())
        logger.info(f"ICMP ping {len(live_list)} live hosts for RTT...")
        with ThreadPoolExecutor(max_workers=min(30, len(live_list))) as ex:
            futs = [ex.submit(ping_live, ip) for ip in live_list]
            for fut in as_completed(futs):
                try:
                    fut.result(timeout=3)
                except Exception:
                    pass

    # Report final progress
    if progress_callback:
        progress_callback(total, total, "done")

    # ── Build device list ─────────────────────────────────────────────
    devices = []
    for ip_str, rtt in found_ips.items():
        mac = arp_table.get(ip_str, "")
        vendor = ""
        if mac:
            from core.mac_vendors import lookup_vendor
            vendor, _ = lookup_vendor(mac)
        devices.append(DiscoveredDevice(
            ip_address=ip_str,
            mac_address=mac,
            vendor=vendor,
            is_reachable=True,
            response_time_ms=rtt,
        ))

    logger.info(f"Ping sweep complete: {len(devices)} devices found")
    return devices
