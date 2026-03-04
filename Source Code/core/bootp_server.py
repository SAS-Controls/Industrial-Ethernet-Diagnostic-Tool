"""
SAS Network Diagnostic Tool — BOOTP Configuration Server
Listens for BOOTP requests from unconfigured devices (like Allen-Bradley
modules in BOOTP mode) and allows the user to assign IP addresses.

This replicates the functionality of Rockwell's BOOTP/DHCP Server utility.

BOOTP operates on UDP port 67 (server) / 68 (client).
Requires admin/elevated privileges to bind to port 67.
"""

import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict

logger = logging.getLogger(__name__)

# BOOTP/DHCP message types
BOOTREQUEST = 1
BOOTREPLY = 2


@dataclass
class BOOTPRequest:
    """A BOOTP request from an unconfigured device."""
    timestamp: datetime
    mac_address: str
    transaction_id: int
    client_ip: str = "0.0.0.0"
    hostname: str = ""
    vendor_class: str = ""
    raw_packet: bytes = b""

    @property
    def mac_display(self) -> str:
        return self.mac_address.upper()


@dataclass
class BOOTPAssignment:
    """An IP assignment to send back to a device."""
    mac_address: str
    ip_address: str
    subnet_mask: str = "255.255.255.0"
    gateway: str = ""
    dns: str = ""
    hostname: str = ""
    assigned_at: Optional[datetime] = None
    sent: bool = False


@dataclass
class BOOTPServerStatus:
    """Current server status."""
    running: bool = False
    bind_address: str = ""
    requests_seen: int = 0
    assignments_sent: int = 0
    error: str = ""
    unique_macs: int = 0


class BOOTPServer:
    """
    BOOTP server that listens for requests and sends configured replies.

    Callbacks:
      on_request(BOOTPRequest)   — new BOOTP request received
      on_status(BOOTPServerStatus) — server status changed
      on_error(str)              — error occurred
    """

    def __init__(self):
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # MAC → assignment mapping
        self._assignments: Dict[str, BOOTPAssignment] = {}
        # MAC → last request (for display/tracking)
        self._requests: Dict[str, BOOTPRequest] = {}

        self._status = BOOTPServerStatus()

        self.on_request: Optional[Callable[[BOOTPRequest], None]] = None
        self.on_status: Optional[Callable[[BOOTPServerStatus], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> BOOTPServerStatus:
        return self._status

    @property
    def pending_requests(self) -> Dict[str, BOOTPRequest]:
        with self._lock:
            return dict(self._requests)

    def set_assignment(self, mac: str, ip: str, mask: str = "255.255.255.0",
                       gateway: str = "", dns: str = "", hostname: str = ""):
        """Configure an IP assignment for a specific MAC address."""
        mac_normalized = mac.upper().replace("-", ":").replace(".", ":")
        with self._lock:
            self._assignments[mac_normalized] = BOOTPAssignment(
                mac_address=mac_normalized, ip_address=ip,
                subnet_mask=mask, gateway=gateway, dns=dns,
                hostname=hostname,
            )
        logger.info(f"BOOTP assignment set: {mac_normalized} → {ip}/{mask}")

    def remove_assignment(self, mac: str):
        """Remove an IP assignment."""
        mac_normalized = mac.upper().replace("-", ":").replace(".", ":")
        with self._lock:
            self._assignments.pop(mac_normalized, None)

    def start(self, bind_addr: str = "0.0.0.0"):
        """Start the BOOTP server."""
        if self._running:
            self.stop()

        self._status = BOOTPServerStatus(bind_address=bind_addr)

        def _serve():
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self._socket.settimeout(1.0)
                self._socket.bind((bind_addr, 67))

                self._running = True
                self._status.running = True
                self._status.error = ""
                self._emit_status()
                logger.info(f"BOOTP server started on {bind_addr}:67")

                while self._running:
                    try:
                        data, addr = self._socket.recvfrom(1024)
                        if len(data) >= 236:  # Minimum BOOTP packet size
                            self._handle_packet(data, addr)
                    except socket.timeout:
                        continue
                    except OSError:
                        if self._running:
                            logger.error("Socket error in BOOTP server")
                        break

            except PermissionError:
                err = "Admin/elevated privileges required to bind to port 67"
                logger.error(err)
                self._status.error = err
                self._emit_status()
                self._emit_error(err)
            except OSError as e:
                err = f"Cannot start BOOTP server: {e}"
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
        """Stop the BOOTP server."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._status.running = False
        self._emit_status()
        logger.info("BOOTP server stopped")

    def _handle_packet(self, data: bytes, addr):
        """Parse and handle a BOOTP request packet."""
        try:
            op = data[0]
            if op != BOOTREQUEST:
                return

            htype = data[1]
            hlen = data[2]
            xid = struct.unpack("!I", data[4:8])[0]
            ciaddr = socket.inet_ntoa(data[12:16])
            chaddr = data[28:28 + hlen]
            mac_str = ":".join(f"{b:02X}" for b in chaddr)

            # Extract hostname from sname field (bytes 44-107)
            sname = data[44:108].split(b"\x00")[0].decode("ascii", errors="replace").strip()

            # Extract vendor class from options if present (after byte 236)
            vendor_class = ""
            if len(data) > 240:
                # Check for DHCP magic cookie
                if data[236:240] == b"\x63\x82\x53\x63":
                    vendor_class = self._parse_vendor_class(data[240:])

            req = BOOTPRequest(
                timestamp=datetime.now(),
                mac_address=mac_str,
                transaction_id=xid,
                client_ip=ciaddr,
                hostname=sname,
                vendor_class=vendor_class,
                raw_packet=data,
            )

            with self._lock:
                self._requests[mac_str] = req
                self._status.requests_seen += 1
                self._status.unique_macs = len(self._requests)

            self._emit_status()
            self._emit_request(req)
            logger.info(f"BOOTP request from {mac_str} (xid={xid:#x})")

            # Check if we have an assignment for this MAC
            with self._lock:
                assignment = self._assignments.get(mac_str)

            if assignment:
                self._send_reply(data, assignment, addr)

        except Exception as e:
            logger.error(f"Error handling BOOTP packet: {e}", exc_info=True)

    def _send_reply(self, request_data: bytes, assignment: BOOTPAssignment, addr):
        """Send a BOOTP reply with the assigned IP."""
        try:
            reply = bytearray(300)

            # Copy header fields from request
            reply[0] = BOOTREPLY              # op
            reply[1] = request_data[1]        # htype
            reply[2] = request_data[2]        # hlen
            reply[3] = 0                      # hops
            reply[4:8] = request_data[4:8]    # xid
            reply[8:10] = b"\x00\x00"         # secs
            reply[10:12] = b"\x00\x00"        # flags

            # yiaddr — your (client) IP address
            reply[16:20] = socket.inet_aton(assignment.ip_address)

            # siaddr — server IP (our IP)
            if self._socket:
                try:
                    our_ip = self._socket.getsockname()[0]
                    if our_ip and our_ip != "0.0.0.0":
                        reply[20:24] = socket.inet_aton(our_ip)
                except Exception:
                    pass

            # chaddr — client hardware address (copy from request)
            reply[28:44] = request_data[28:44]

            # DHCP magic cookie
            reply[236:240] = b"\x63\x82\x53\x63"

            # DHCP options
            idx = 240
            # Option 53: DHCP Message Type = OFFER (2)
            reply[idx:idx+3] = bytes([53, 1, 2])
            idx += 3
            # Option 1: Subnet Mask
            reply[idx:idx+2] = bytes([1, 4])
            reply[idx+2:idx+6] = socket.inet_aton(assignment.subnet_mask)
            idx += 6
            # Option 3: Gateway (if specified)
            if assignment.gateway:
                reply[idx:idx+2] = bytes([3, 4])
                reply[idx+2:idx+6] = socket.inet_aton(assignment.gateway)
                idx += 6
            # Option 6: DNS (if specified)
            if assignment.dns:
                reply[idx:idx+2] = bytes([6, 4])
                reply[idx+2:idx+6] = socket.inet_aton(assignment.dns)
                idx += 6
            # Option 51: Lease time (infinite for BOOTP)
            reply[idx:idx+2] = bytes([51, 4])
            reply[idx+2:idx+6] = struct.pack("!I", 0xFFFFFFFF)
            idx += 6
            # End option
            reply[idx] = 255
            idx += 1

            # Send as broadcast
            self._socket.sendto(bytes(reply[:idx]),
                              ("255.255.255.255", 68))

            assignment.sent = True
            assignment.assigned_at = datetime.now()
            with self._lock:
                self._status.assignments_sent += 1
            self._emit_status()

            logger.info(
                f"BOOTP reply sent: {assignment.mac_address} → "
                f"{assignment.ip_address}/{assignment.subnet_mask}"
            )

        except Exception as e:
            logger.error(f"Failed to send BOOTP reply: {e}", exc_info=True)
            self._emit_error(f"Reply failed: {e}")

    def _parse_vendor_class(self, options_data: bytes) -> str:
        """Parse DHCP option 60 (Vendor Class Identifier)."""
        i = 0
        while i < len(options_data) - 1:
            opt = options_data[i]
            if opt == 255:
                break
            if opt == 0:
                i += 1
                continue
            length = options_data[i + 1]
            if opt == 60:
                return options_data[i+2:i+2+length].decode("ascii", errors="replace")
            i += 2 + length
        return ""

    def _emit_request(self, req: BOOTPRequest):
        if self.on_request:
            try:
                self.on_request(req)
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
