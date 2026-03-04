"""
SAS Network Diagnostic Tool — TCP/UDP Socket Tester Engine
Provides client and server modes for testing TCP and UDP connections.

Used to verify connectivity, test firewall rules, and debug communication
between industrial devices and host applications.
"""

import logging
import socket
import select
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, List

logger = logging.getLogger(__name__)


class Protocol(Enum):
    TCP = "TCP"
    UDP = "UDP"


class Mode(Enum):
    CLIENT = "Client"
    SERVER = "Server"


@dataclass
class SocketMessage:
    """A single sent or received message."""
    timestamp: datetime
    direction: str        # "TX" or "RX"
    data: bytes
    remote_addr: str = ""
    remote_port: int = 0

    @property
    def hex_str(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def ascii_str(self) -> str:
        return "".join(chr(b) if 32 <= b < 127 else "." for b in self.data)

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class ConnectionInfo:
    """Current connection status."""
    connected: bool = False
    local_addr: str = ""
    local_port: int = 0
    remote_addr: str = ""
    remote_port: int = 0
    protocol: Protocol = Protocol.TCP
    mode: Mode = Mode.CLIENT
    error: str = ""
    client_count: int = 0  # Server mode: number of connected clients


class SocketTesterEngine:
    """
    TCP/UDP socket tester supporting client and server modes.

    Events are delivered via callbacks:
      on_message(SocketMessage)  — new message sent/received
      on_status(ConnectionInfo)  — connection status changed
      on_error(str)              — error occurred
    """

    def __init__(self):
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._server_clients: List[socket.socket] = []
        self._lock = threading.Lock()

        # Callbacks
        self.on_message: Optional[Callable[[SocketMessage], None]] = None
        self.on_status: Optional[Callable[[ConnectionInfo], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        self._info = ConnectionInfo()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def connection_info(self) -> ConnectionInfo:
        return self._info

    # ── Client Mode ──────────────────────────────────────────────────────────

    def connect_client(self, host: str, port: int, protocol: Protocol,
                       timeout: float = 5.0):
        """Connect as a client to a remote host."""
        if self._running:
            self.disconnect()

        self._info = ConnectionInfo(
            protocol=protocol, mode=Mode.CLIENT,
            remote_addr=host, remote_port=port,
        )

        def _connect():
            try:
                if protocol == Protocol.TCP:
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._socket.settimeout(timeout)
                    logger.info(f"TCP connecting to {host}:{port}...")
                    self._socket.connect((host, port))
                    self._socket.settimeout(1.0)  # For recv polling
                    local = self._socket.getsockname()
                    self._info.connected = True
                    self._info.local_addr = local[0]
                    self._info.local_port = local[1]
                    self._info.error = ""
                    self._running = True
                    self._emit_status()
                    logger.info(f"TCP connected to {host}:{port}")
                    self._tcp_client_loop()

                else:  # UDP
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._socket.settimeout(1.0)
                    # Bind to any available port
                    self._socket.bind(("", 0))
                    local = self._socket.getsockname()
                    self._info.connected = True
                    self._info.local_addr = local[0]
                    self._info.local_port = local[1]
                    self._info.error = ""
                    self._running = True
                    self._emit_status()
                    logger.info(f"UDP client ready on port {local[1]}, target {host}:{port}")
                    self._udp_client_loop(host, port)

            except Exception as e:
                logger.error(f"Connection failed: {e}")
                self._info.connected = False
                self._info.error = str(e)
                self._emit_status()
                self._emit_error(f"Connection failed: {e}")

        self._thread = threading.Thread(target=_connect, daemon=True)
        self._thread.start()

    def _tcp_client_loop(self):
        """Receive loop for TCP client."""
        while self._running and self._socket:
            try:
                data = self._socket.recv(4096)
                if not data:
                    logger.info("TCP connection closed by remote")
                    break
                msg = SocketMessage(
                    timestamp=datetime.now(), direction="RX", data=data,
                    remote_addr=self._info.remote_addr,
                    remote_port=self._info.remote_port,
                )
                self._emit_message(msg)
            except socket.timeout:
                continue
            except OSError:
                break

        self._info.connected = False
        self._running = False
        self._emit_status()

    def _udp_client_loop(self, host: str, port: int):
        """Receive loop for UDP client."""
        while self._running and self._socket:
            try:
                data, addr = self._socket.recvfrom(4096)
                msg = SocketMessage(
                    timestamp=datetime.now(), direction="RX", data=data,
                    remote_addr=addr[0], remote_port=addr[1],
                )
                self._emit_message(msg)
            except socket.timeout:
                continue
            except OSError:
                break

        self._info.connected = False
        self._running = False
        self._emit_status()

    # ── Server Mode ──────────────────────────────────────────────────────────

    def start_server(self, bind_addr: str, port: int, protocol: Protocol):
        """Start listening as a server."""
        if self._running:
            self.disconnect()

        self._info = ConnectionInfo(
            protocol=protocol, mode=Mode.SERVER,
            local_addr=bind_addr, local_port=port,
        )

        def _serve():
            try:
                if protocol == Protocol.TCP:
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self._socket.settimeout(1.0)
                    self._socket.bind((bind_addr, port))
                    self._socket.listen(5)
                    self._info.connected = True
                    self._info.error = ""
                    self._running = True
                    self._emit_status()
                    logger.info(f"TCP server listening on {bind_addr}:{port}")
                    self._tcp_server_loop()

                else:  # UDP
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self._socket.settimeout(1.0)
                    self._socket.bind((bind_addr, port))
                    self._info.connected = True
                    self._info.error = ""
                    self._running = True
                    self._emit_status()
                    logger.info(f"UDP server listening on {bind_addr}:{port}")
                    self._udp_server_loop()

            except Exception as e:
                logger.error(f"Server start failed: {e}")
                self._info.connected = False
                self._info.error = str(e)
                self._emit_status()
                self._emit_error(f"Server failed: {e}")

        self._thread = threading.Thread(target=_serve, daemon=True)
        self._thread.start()

    def _tcp_server_loop(self):
        """Accept loop for TCP server."""
        while self._running and self._socket:
            try:
                client_sock, addr = self._socket.accept()
                client_sock.settimeout(1.0)
                logger.info(f"TCP client connected from {addr[0]}:{addr[1]}")
                with self._lock:
                    self._server_clients.append(client_sock)
                    self._info.client_count = len(self._server_clients)
                self._emit_status()

                # Spawn a receive thread for this client
                t = threading.Thread(
                    target=self._tcp_server_client_handler,
                    args=(client_sock, addr), daemon=True,
                )
                t.start()

            except socket.timeout:
                continue
            except OSError:
                break

        self._running = False
        self._info.connected = False
        self._emit_status()

    def _tcp_server_client_handler(self, client_sock: socket.socket, addr):
        """Handle a single TCP server client connection."""
        while self._running:
            try:
                data = client_sock.recv(4096)
                if not data:
                    break
                msg = SocketMessage(
                    timestamp=datetime.now(), direction="RX", data=data,
                    remote_addr=addr[0], remote_port=addr[1],
                )
                self._emit_message(msg)
            except socket.timeout:
                continue
            except OSError:
                break

        logger.info(f"TCP client disconnected: {addr[0]}:{addr[1]}")
        with self._lock:
            if client_sock in self._server_clients:
                self._server_clients.remove(client_sock)
            self._info.client_count = len(self._server_clients)
        try:
            client_sock.close()
        except Exception:
            pass
        self._emit_status()

    def _udp_server_loop(self):
        """Receive loop for UDP server."""
        while self._running and self._socket:
            try:
                data, addr = self._socket.recvfrom(4096)
                msg = SocketMessage(
                    timestamp=datetime.now(), direction="RX", data=data,
                    remote_addr=addr[0], remote_port=addr[1],
                )
                self._emit_message(msg)
            except socket.timeout:
                continue
            except OSError:
                break

        self._running = False
        self._info.connected = False
        self._emit_status()

    # ── Send Data ────────────────────────────────────────────────────────────

    def send(self, data: bytes, remote_addr: str = "", remote_port: int = 0) -> bool:
        """Send data. For UDP client, use the target addr/port from connect."""
        if not self._socket or not self._running:
            self._emit_error("Not connected")
            return False

        try:
            if self._info.protocol == Protocol.TCP:
                if self._info.mode == Mode.CLIENT:
                    self._socket.sendall(data)
                else:
                    # Server: send to all connected clients
                    with self._lock:
                        for client in list(self._server_clients):
                            try:
                                client.sendall(data)
                            except Exception:
                                pass
            else:  # UDP
                target_addr = remote_addr or self._info.remote_addr
                target_port = remote_port or self._info.remote_port
                if not target_addr or not target_port:
                    self._emit_error("No target address for UDP send")
                    return False
                self._socket.sendto(data, (target_addr, target_port))

            msg = SocketMessage(
                timestamp=datetime.now(), direction="TX", data=data,
                remote_addr=remote_addr or self._info.remote_addr,
                remote_port=remote_port or self._info.remote_port,
            )
            self._emit_message(msg)
            return True

        except Exception as e:
            self._emit_error(f"Send failed: {e}")
            return False

    # ── Disconnect ───────────────────────────────────────────────────────────

    def disconnect(self):
        """Stop and close all connections."""
        self._running = False

        with self._lock:
            for client in self._server_clients:
                try:
                    client.close()
                except Exception:
                    pass
            self._server_clients.clear()

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        self._info.connected = False
        self._info.client_count = 0
        self._emit_status()
        logger.info("Socket tester disconnected")

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _emit_message(self, msg: SocketMessage):
        if self.on_message:
            try:
                self.on_message(msg)
            except Exception:
                pass

    def _emit_status(self):
        if self.on_status:
            try:
                self.on_status(self._info)
            except Exception:
                pass

    def _emit_error(self, msg: str):
        if self.on_error:
            try:
                self.on_error(msg)
            except Exception:
                pass
        logger.error(f"SocketTester: {msg}")
