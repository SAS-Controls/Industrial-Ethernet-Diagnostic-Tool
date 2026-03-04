"""
SAS Network Diagnostic Tool — Lightweight DHCP Server
Turns the laptop into a DHCP server for assigning IPs to industrial devices.

Designed for field use: connect directly to a device or small switch,
enable the server, and devices get IPs automatically.

Requires admin/elevated privileges to bind to port 67.
"""

import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Dict, Tuple
import ipaddress

logger = logging.getLogger(__name__)


@dataclass
class DHCPLease:
    """A DHCP lease record."""
    mac_address: str
    ip_address: str
    hostname: str = ""
    lease_start: datetime = field(default_factory=datetime.now)
    lease_duration: int = 3600  # seconds
    state: str = "active"  # active, expired, offered

    @property
    def expires_at(self) -> datetime:
        return self.lease_start + timedelta(seconds=self.lease_duration)

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    @property
    def remaining_str(self) -> str:
        remaining = (self.expires_at - datetime.now()).total_seconds()
        if remaining <= 0:
            return "Expired"
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        if mins > 60:
            return f"{mins // 60}h {mins % 60}m"
        return f"{mins}m {secs}s"


@dataclass
class DHCPServerConfig:
    """DHCP server configuration."""
    pool_start: str = "192.168.1.100"
    pool_end: str = "192.168.1.200"
    subnet_mask: str = "255.255.255.0"
    gateway: str = ""
    dns_primary: str = ""
    dns_secondary: str = ""
    lease_time: int = 3600        # seconds
    domain_name: str = ""
    bind_address: str = "0.0.0.0"


@dataclass
class DHCPServerStatus:
    """Current DHCP server status."""
    running: bool = False
    bind_address: str = ""
    pool_start: str = ""
    pool_end: str = ""
    total_pool_size: int = 0
    leases_active: int = 0
    leases_available: int = 0
    requests_received: int = 0
    offers_sent: int = 0
    acks_sent: int = 0
    error: str = ""


# DHCP message types
DHCPDISCOVER = 1
DHCPOFFER = 2
DHCPREQUEST = 3
DHCPDECLINE = 4
DHCPACK = 5
DHCPNAK = 6
DHCPRELEASE = 7
DHCPINFORM = 8


class DHCPServer:
    """
    Lightweight DHCP server for industrial field use.

    Callbacks:
      on_lease_change(DHCPLease) — lease created/updated/expired
      on_status(DHCPServerStatus) — server status changed
      on_error(str)               — error occurred
    """

    def __init__(self):
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._config = DHCPServerConfig()
        self._leases: Dict[str, DHCPLease] = {}   # MAC → lease
        self._ip_pool: List[str] = []              # Available IPs
        self._offered: Dict[str, str] = {}         # MAC → offered IP (pending ACK)

        self._status = DHCPServerStatus()

        self.on_lease_change: Optional[Callable[[DHCPLease], None]] = None
        self.on_status: Optional[Callable[[DHCPServerStatus], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def config(self) -> DHCPServerConfig:
        return self._config

    @property
    def leases(self) -> Dict[str, DHCPLease]:
        with self._lock:
            return dict(self._leases)

    @property
    def status(self) -> DHCPServerStatus:
        return self._status

    def configure(self, config: DHCPServerConfig):
        """Set server configuration. Must be called before start()."""
        self._config = config
        self._build_pool()

    def _build_pool(self):
        """Build the IP address pool from config."""
        try:
            start = ipaddress.IPv4Address(self._config.pool_start)
            end = ipaddress.IPv4Address(self._config.pool_end)
            self._ip_pool = []
            current = start
            while current <= end:
                self._ip_pool.append(str(current))
                current += 1
            logger.info(f"DHCP pool built: {len(self._ip_pool)} addresses "
                       f"({self._config.pool_start} - {self._config.pool_end})")
        except Exception as e:
            logger.error(f"Invalid DHCP pool config: {e}")
            self._ip_pool = []

    def _get_available_ip(self, mac: str) -> Optional[str]:
        """Get an available IP, preferring previous assignment for the same MAC."""
        with self._lock:
            # Check if this MAC already has a lease
            if mac in self._leases:
                return self._leases[mac].ip_address
            # Check if we already offered an IP
            if mac in self._offered:
                return self._offered[mac]
            # Find a free IP from the pool
            used_ips = set()
            for lease in self._leases.values():
                if not lease.is_expired:
                    used_ips.add(lease.ip_address)
            for ip in self._offered.values():
                used_ips.add(ip)
            for ip in self._ip_pool:
                if ip not in used_ips:
                    return ip
        return None

    def start(self):
        """Start the DHCP server."""
        if self._running:
            self.stop()

        if not self._ip_pool:
            self._build_pool()

        self._status = DHCPServerStatus(
            bind_address=self._config.bind_address,
            pool_start=self._config.pool_start,
            pool_end=self._config.pool_end,
            total_pool_size=len(self._ip_pool),
            leases_available=len(self._ip_pool),
        )

        def _serve():
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self._socket.settimeout(1.0)
                self._socket.bind((self._config.bind_address, 67))

                self._running = True
                self._status.running = True
                self._status.error = ""
                self._emit_status()
                logger.info(f"DHCP server started — pool: "
                          f"{self._config.pool_start}-{self._config.pool_end}")

                # Start lease cleanup thread
                self._cleanup_thread = threading.Thread(
                    target=self._cleanup_loop, daemon=True)
                self._cleanup_thread.start()

                while self._running:
                    try:
                        data, addr = self._socket.recvfrom(1024)
                        if len(data) >= 236:
                            self._handle_packet(data, addr)
                    except socket.timeout:
                        continue
                    except OSError:
                        if self._running:
                            logger.error("Socket error in DHCP server")
                        break

            except PermissionError:
                err = "Admin/elevated privileges required to bind to port 67"
                logger.error(err)
                self._status.error = err
                self._emit_status()
                self._emit_error(err)
            except OSError as e:
                err = f"Cannot start DHCP server: {e}"
                logger.error(err)
                self._status.error = err
                self._emit_status()
                self._emit_error(err)
            finally:
                self._running = False
                self._status.running = False
                self._emit_status()

        self._thread = threading.Thread(target=_serve, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the DHCP server."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._status.running = False
        self._emit_status()
        logger.info("DHCP server stopped")

    def release_lease(self, mac: str):
        """Manually release a lease."""
        with self._lock:
            if mac in self._leases:
                self._leases[mac].state = "expired"
                del self._leases[mac]
                self._update_lease_counts()
        self._emit_status()

    def _handle_packet(self, data: bytes, addr):
        """Parse and handle a DHCP packet."""
        try:
            op = data[0]
            if op != 1:  # Only handle requests
                return

            hlen = data[2]
            xid = data[4:8]
            chaddr = data[28:28 + hlen]
            mac_str = ":".join(f"{b:02X}" for b in chaddr)

            # Parse DHCP options
            msg_type = None
            requested_ip = None
            hostname = ""

            if len(data) > 240 and data[236:240] == b"\x63\x82\x53\x63":
                i = 240
                while i < len(data) - 1:
                    opt = data[i]
                    if opt == 255:
                        break
                    if opt == 0:
                        i += 1
                        continue
                    length = data[i + 1]
                    if opt == 53 and length == 1:
                        msg_type = data[i + 2]
                    elif opt == 50 and length == 4:
                        requested_ip = socket.inet_ntoa(data[i+2:i+6])
                    elif opt == 12:
                        hostname = data[i+2:i+2+length].decode("ascii", errors="replace")
                    i += 2 + length

            self._status.requests_received += 1

            if msg_type == DHCPDISCOVER:
                self._handle_discover(data, xid, mac_str, hostname)
            elif msg_type == DHCPREQUEST:
                self._handle_request(data, xid, mac_str, requested_ip, hostname)
            elif msg_type == DHCPRELEASE:
                self.release_lease(mac_str)
            elif msg_type is None:
                # Pure BOOTP request (no DHCP options) — treat as discover
                self._handle_discover(data, xid, mac_str, hostname)

        except Exception as e:
            logger.error(f"Error handling DHCP packet: {e}", exc_info=True)

    def _handle_discover(self, request: bytes, xid: bytes, mac: str, hostname: str):
        """Handle DHCPDISCOVER — send DHCPOFFER."""
        ip = self._get_available_ip(mac)
        if not ip:
            logger.warning(f"No IPs available for {mac}")
            return

        with self._lock:
            self._offered[mac] = ip

        self._send_reply(request, xid, mac, ip, DHCPOFFER)
        self._status.offers_sent += 1
        self._emit_status()
        logger.info(f"DHCP OFFER: {mac} → {ip}")

    def _handle_request(self, request: bytes, xid: bytes, mac: str,
                        requested_ip: Optional[str], hostname: str):
        """Handle DHCPREQUEST — send DHCPACK or DHCPNAK."""
        with self._lock:
            offered = self._offered.get(mac)

        # Determine which IP to assign
        assign_ip = requested_ip or offered
        if not assign_ip:
            assign_ip = self._get_available_ip(mac)

        if not assign_ip or assign_ip not in self._ip_pool:
            self._send_reply(request, xid, mac, "0.0.0.0", DHCPNAK)
            return

        # Create lease
        lease = DHCPLease(
            mac_address=mac, ip_address=assign_ip,
            hostname=hostname,
            lease_duration=self._config.lease_time,
            state="active",
        )
        with self._lock:
            self._leases[mac] = lease
            self._offered.pop(mac, None)
            self._update_lease_counts()

        self._send_reply(request, xid, mac, assign_ip, DHCPACK)
        self._status.acks_sent += 1
        self._emit_status()
        self._emit_lease(lease)
        logger.info(f"DHCP ACK: {mac} → {assign_ip} (lease {self._config.lease_time}s)")

    def _send_reply(self, request: bytes, xid: bytes, mac: str,
                    ip: str, msg_type: int):
        """Build and send a DHCP reply."""
        try:
            reply = bytearray(300)
            reply[0] = 2                          # BOOTREPLY
            reply[1] = request[1]                 # htype
            reply[2] = request[2]                 # hlen
            reply[4:8] = xid                      # xid

            if ip and ip != "0.0.0.0":
                reply[16:20] = socket.inet_aton(ip)   # yiaddr

            # siaddr — server IP
            try:
                our_ip = self._socket.getsockname()[0]
                if our_ip and our_ip != "0.0.0.0":
                    reply[20:24] = socket.inet_aton(our_ip)
            except Exception:
                pass

            reply[28:44] = request[28:44]         # chaddr

            # DHCP magic cookie
            reply[236:240] = b"\x63\x82\x53\x63"

            idx = 240
            # Option 53: Message Type
            reply[idx:idx+3] = bytes([53, 1, msg_type])
            idx += 3

            if msg_type in (DHCPOFFER, DHCPACK):
                # Option 1: Subnet Mask
                reply[idx:idx+2] = bytes([1, 4])
                reply[idx+2:idx+6] = socket.inet_aton(self._config.subnet_mask)
                idx += 6
                # Option 51: Lease Time
                reply[idx:idx+2] = bytes([51, 4])
                reply[idx+2:idx+6] = struct.pack("!I", self._config.lease_time)
                idx += 6
                # Option 54: Server Identifier
                try:
                    our_ip = self._socket.getsockname()[0]
                    if our_ip and our_ip != "0.0.0.0":
                        reply[idx:idx+2] = bytes([54, 4])
                        reply[idx+2:idx+6] = socket.inet_aton(our_ip)
                        idx += 6
                except Exception:
                    pass
                # Option 3: Gateway
                if self._config.gateway:
                    reply[idx:idx+2] = bytes([3, 4])
                    reply[idx+2:idx+6] = socket.inet_aton(self._config.gateway)
                    idx += 6
                # Option 6: DNS
                if self._config.dns_primary:
                    dns_data = socket.inet_aton(self._config.dns_primary)
                    if self._config.dns_secondary:
                        dns_data += socket.inet_aton(self._config.dns_secondary)
                    reply[idx] = 6
                    reply[idx+1] = len(dns_data)
                    reply[idx+2:idx+2+len(dns_data)] = dns_data
                    idx += 2 + len(dns_data)

            # End option
            reply[idx] = 255
            idx += 1

            self._socket.sendto(bytes(reply[:idx]),
                              ("255.255.255.255", 68))

        except Exception as e:
            logger.error(f"Failed to send DHCP reply: {e}", exc_info=True)

    def _cleanup_loop(self):
        """Periodically clean up expired leases."""
        while self._running:
            time.sleep(30)
            with self._lock:
                expired = [
                    mac for mac, lease in self._leases.items()
                    if lease.is_expired
                ]
                for mac in expired:
                    self._leases[mac].state = "expired"
                    del self._leases[mac]
                if expired:
                    self._update_lease_counts()
            if expired:
                self._emit_status()

    def _update_lease_counts(self):
        """Update lease counts in status (call under lock)."""
        active = sum(1 for l in self._leases.values() if not l.is_expired)
        self._status.leases_active = active
        self._status.leases_available = len(self._ip_pool) - active

    def _emit_lease(self, lease: DHCPLease):
        if self.on_lease_change:
            try:
                self.on_lease_change(lease)
            except Exception:
                pass

    def _emit_status(self):
        if self.on_status:
            try:
                self.on_status(self._status)
            except Exception:
                pass

    def _emit_error(self, msg: str):
        if self.on_error:
            try:
                self.on_error(msg)
            except Exception:
                pass
