"""
SAS Network Diagnostic Tool — Multi-Device Monitor Engine
Monitors multiple Ethernet devices simultaneously with ping + CIP probes.
Collects time-series trend data for charting and analytics.
"""

import logging
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class DeviceTarget:
    """A device being monitored."""
    ip: str
    label: str = ""            # User-friendly name (optional)
    color: str = ""            # Chart line color (auto-assigned if blank)

    @property
    def display_name(self) -> str:
        return self.label if self.label else self.ip


@dataclass
class MultiPollSample:
    """One poll cycle across all monitored devices."""
    timestamp: datetime
    elapsed_seconds: float
    results: Dict[str, "DevicePollResult"] = field(default_factory=dict)


@dataclass
class DevicePollResult:
    """Result of polling a single device in one cycle."""
    ip: str
    ping_success: bool = False
    ping_time_ms: float = 0.0
    ping_error: str = ""
    cip_success: bool = False
    cip_time_ms: float = 0.0
    cip_error: str = ""
    product_name: str = ""
    vendor_name: str = ""

    @property
    def is_reachable(self) -> bool:
        return self.ping_success or self.cip_success

    @property
    def best_response_ms(self) -> float:
        times = []
        if self.ping_success:
            times.append(self.ping_time_ms)
        if self.cip_success:
            times.append(self.cip_time_ms)
        return min(times) if times else 0.0


@dataclass
class DeviceAnalytics:
    """Accumulated analytics for a single device over the monitoring session."""
    ip: str
    label: str = ""
    total_polls: int = 0
    ping_success_count: int = 0
    ping_fail_count: int = 0
    cip_success_count: int = 0
    cip_fail_count: int = 0
    ping_min_ms: float = 0.0
    ping_max_ms: float = 0.0
    ping_avg_ms: float = 0.0
    ping_total_ms: float = 0.0
    cip_min_ms: float = 0.0
    cip_max_ms: float = 0.0
    cip_avg_ms: float = 0.0
    cip_total_ms: float = 0.0
    outage_count: int = 0
    longest_outage_sec: float = 0.0
    last_status: str = "unknown"
    product_name: str = ""
    vendor_name: str = ""
    # Outage tracking internals
    _in_outage: bool = False
    _outage_start: float = 0.0

    @property
    def uptime_pct(self) -> float:
        if self.total_polls == 0:
            return 0.0
        return (self.ping_success_count / self.total_polls) * 100.0

    @property
    def ping_loss_pct(self) -> float:
        if self.total_polls == 0:
            return 0.0
        return (self.ping_fail_count / self.total_polls) * 100.0


@dataclass
class TrendPoint:
    """Single data point for the trend chart."""
    timestamp: datetime
    values: Dict[str, Optional[float]] = field(default_factory=dict)


# ── Default Chart Colors (matching SAS Trend Tool palette) ───────────────────

CHART_COLORS = [
    "#0070BB",  # SAS Blue
    "#E8722A",  # SAS Orange
    "#22C55E",  # Green
    "#EF4444",  # Red
    "#A855F7",  # Purple
    "#06B6D4",  # Cyan
    "#F59E0B",  # Amber
    "#EC4899",  # Pink
    "#14B8A6",  # Teal
    "#8B5CF6",  # Violet
    "#F97316",  # Orange-red
    "#6366F1",  # Indigo
    "#10B981",  # Emerald
    "#F43F5E",  # Rose
    "#84CC16",  # Lime
    "#0EA5E9",  # Sky
]


class MultiDeviceMonitor:
    """
    Monitors multiple devices simultaneously.
    Collects ping + CIP response times for trend charting.
    """

    def __init__(self):
        self._targets: List[DeviceTarget] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._start_time: Optional[datetime] = None
        self._poll_interval: float = 1.0
        self._timeout: float = 2.0

        # Data storage
        self._samples: List[MultiPollSample] = []
        self._trend_data: List[TrendPoint] = []
        self._analytics: Dict[str, DeviceAnalytics] = {}

        # Callbacks
        self._on_sample: Optional[Callable[[MultiPollSample], None]] = None
        self._on_status: Optional[Callable[[str], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

    # ── Configuration ────────────────────────────────────────────────────────

    def set_targets(self, targets: List[DeviceTarget]):
        """Set the list of devices to monitor."""
        # Auto-assign colors if not set
        for i, t in enumerate(targets):
            if not t.color:
                t.color = CHART_COLORS[i % len(CHART_COLORS)]
        self._targets = list(targets)

    def set_poll_interval(self, seconds: float):
        self._poll_interval = max(0.5, seconds)

    def set_timeout(self, seconds: float):
        self._timeout = max(0.5, seconds)

    def set_on_sample(self, cb: Callable[[MultiPollSample], None]):
        self._on_sample = cb

    def set_on_status(self, cb: Callable[[str], None]):
        self._on_status = cb

    def set_on_error(self, cb: Callable[[str], None]):
        self._on_error = cb

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def targets(self) -> List[DeviceTarget]:
        return list(self._targets)

    @property
    def sample_count(self) -> int:
        with self._lock:
            return len(self._samples)

    @property
    def elapsed_seconds(self) -> float:
        if not self._start_time:
            return 0.0
        return (datetime.now() - self._start_time).total_seconds()

    # ── Start / Stop ─────────────────────────────────────────────────────────

    def start(self):
        """Start monitoring all target devices."""
        if self._running or not self._targets:
            return

        self._running = True
        self._start_time = datetime.now()
        self._samples = []
        self._trend_data = []

        # Initialize analytics for each target
        self._analytics = {}
        for t in self._targets:
            self._analytics[t.ip] = DeviceAnalytics(ip=t.ip, label=t.display_name)

        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

        if self._on_status:
            try:
                self._on_status(f"Monitoring {len(self._targets)} devices")
            except Exception:
                pass

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        # Close any outages that were in progress
        now = time.time()
        for a in self._analytics.values():
            if a._in_outage:
                outage_dur = now - a._outage_start
                if outage_dur > a.longest_outage_sec:
                    a.longest_outage_sec = outage_dur
                a._in_outage = False

        if self._on_status:
            try:
                self._on_status("Monitoring stopped")
            except Exception:
                pass

    def clear(self):
        """Clear all collected data."""
        with self._lock:
            self._samples = []
            self._trend_data = []
            self._analytics = {}
            self._start_time = None

    # ── Poll Loop ────────────────────────────────────────────────────────────

    def _poll_loop(self):
        """Background thread: poll all devices at the configured interval."""
        while self._running:
            cycle_start = time.perf_counter()

            try:
                now = datetime.now()
                elapsed = (now - self._start_time).total_seconds() if self._start_time else 0.0

                sample = MultiPollSample(timestamp=now, elapsed_seconds=elapsed)
                trend_point = TrendPoint(timestamp=now)

                # Poll each device concurrently using threads
                threads = []
                results: Dict[str, DevicePollResult] = {}
                results_lock = threading.Lock()

                def poll_device(target: DeviceTarget):
                    result = self._poll_single(target)
                    with results_lock:
                        results[target.ip] = result

                for t in self._targets:
                    th = threading.Thread(target=poll_device, args=(t,), daemon=True)
                    threads.append(th)
                    th.start()

                for th in threads:
                    th.join(timeout=self._timeout + 1.0)

                # Assemble results
                for t in self._targets:
                    ip = t.ip
                    result = results.get(ip)
                    if result is None:
                        result = DevicePollResult(ip=ip, ping_error="timeout")
                    sample.results[ip] = result

                    # Trend data: use ping_time_ms (None if failed)
                    if result.ping_success:
                        trend_point.values[ip] = result.ping_time_ms
                    else:
                        trend_point.values[ip] = None

                    # Update analytics
                    self._update_analytics(ip, result)

                with self._lock:
                    self._samples.append(sample)
                    self._trend_data.append(trend_point)

                if self._on_sample:
                    try:
                        self._on_sample(sample)
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Poll cycle error: {e}", exc_info=True)
                if self._on_error:
                    try:
                        self._on_error(str(e))
                    except Exception:
                        pass

            # Sleep for remainder of interval
            elapsed_cycle = time.perf_counter() - cycle_start
            sleep_time = max(0.05, self._poll_interval - elapsed_cycle)
            time.sleep(sleep_time)

    def _poll_single(self, target: DeviceTarget) -> DevicePollResult:
        """Poll a single device: ping + CIP identity."""
        result = DevicePollResult(ip=target.ip)

        # ICMP ping
        try:
            ok, ms = self._ping(target.ip, self._timeout)
            result.ping_success = ok
            result.ping_time_ms = ms
            if not ok:
                result.ping_error = "timeout"
        except Exception as e:
            result.ping_error = str(e)

        # CIP ListIdentity (EtherNet/IP)
        try:
            ok, ms, identity = self._cip_list_identity(target.ip, self._timeout)
            result.cip_success = ok
            result.cip_time_ms = ms
            if identity:
                result.product_name = identity.get("product_name", "")
                result.vendor_name = identity.get("vendor_name", "")
        except Exception as e:
            result.cip_error = str(e)

        return result

    def _update_analytics(self, ip: str, result: DevicePollResult):
        """Update running analytics for a device."""
        a = self._analytics.get(ip)
        if not a:
            return

        a.total_polls += 1

        # Ping stats
        if result.ping_success:
            a.ping_success_count += 1
            ms = result.ping_time_ms
            a.ping_total_ms += ms
            if a.ping_min_ms == 0 or ms < a.ping_min_ms:
                a.ping_min_ms = ms
            if ms > a.ping_max_ms:
                a.ping_max_ms = ms
            a.ping_avg_ms = a.ping_total_ms / a.ping_success_count
        else:
            a.ping_fail_count += 1

        # CIP stats
        if result.cip_success:
            a.cip_success_count += 1
            ms = result.cip_time_ms
            a.cip_total_ms += ms
            if a.cip_min_ms == 0 or ms < a.cip_min_ms:
                a.cip_min_ms = ms
            if ms > a.cip_max_ms:
                a.cip_max_ms = ms
            a.cip_avg_ms = a.cip_total_ms / a.cip_success_count
            if result.product_name:
                a.product_name = result.product_name
            if result.vendor_name:
                a.vendor_name = result.vendor_name
        else:
            a.cip_fail_count += 1

        # Outage tracking
        reachable = result.is_reachable
        a.last_status = "online" if reachable else "offline"

        now = time.time()
        if not reachable:
            if not a._in_outage:
                a._in_outage = True
                a._outage_start = now
                a.outage_count += 1
        else:
            if a._in_outage:
                outage_dur = now - a._outage_start
                if outage_dur > a.longest_outage_sec:
                    a.longest_outage_sec = outage_dur
                a._in_outage = False

    # ── Data Access ──────────────────────────────────────────────────────────

    def get_trend_data(self) -> Dict[str, Tuple[List[datetime], List[Optional[float]]]]:
        """Return trend data in chart-friendly format: {ip: (times, values)}."""
        with self._lock:
            result = {}
            for t in self._targets:
                ip = t.ip
                times = []
                vals = []
                for pt in self._trend_data:
                    times.append(pt.timestamp)
                    v = pt.values.get(ip)
                    vals.append(v if v is not None else float('nan'))
                result[ip] = (times, vals)
            return result

    def get_analytics(self) -> Dict[str, DeviceAnalytics]:
        """Return analytics for all devices."""
        return dict(self._analytics)

    def get_samples_snapshot(self) -> List[MultiPollSample]:
        with self._lock:
            return list(self._samples)

    # ── Network Probes ───────────────────────────────────────────────────────

    @staticmethod
    def _ping(host: str, timeout: float) -> Tuple[bool, float]:
        """ICMP ping a host. Returns (success, time_ms)."""
        try:
            timeout_ms = int(timeout * 1000)
            result = subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout_ms), host],
                capture_output=True, text=True, timeout=timeout + 2,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
            if result.returncode == 0:
                output = result.stdout
                # Parse "time=Xms" or "time<1ms"
                for line in output.splitlines():
                    if "time=" in line.lower() or "time<" in line.lower():
                        lower = line.lower()
                        if "time<" in lower:
                            return True, 0.5
                        idx = lower.index("time=")
                        chunk = lower[idx + 5:]
                        ms_str = ""
                        for ch in chunk:
                            if ch.isdigit() or ch == '.':
                                ms_str += ch
                            else:
                                break
                        if ms_str:
                            return True, float(ms_str)
                        return True, 0.0
                return True, 0.0
            return False, 0.0
        except subprocess.TimeoutExpired:
            return False, 0.0
        except Exception:
            return False, 0.0

    @staticmethod
    def _cip_list_identity(host: str, timeout: float) -> Tuple[bool, float, Optional[dict]]:
        """Send EtherNet/IP ListIdentity broadcast to a specific host."""
        EIP_PORT = 44818
        LIST_IDENTITY = (
            b"\x63\x00"        # Command: ListIdentity
            b"\x00\x00"        # Length: 0
            b"\x00\x00\x00\x00"  # Session: 0
            b"\x00\x00\x00\x00"  # Status: 0
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Sender context
            b"\x00\x00\x00\x00"  # Options: 0
        )
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            start = time.perf_counter()
            sock.sendto(LIST_IDENTITY, (host, EIP_PORT))
            data, _ = sock.recvfrom(1024)
            elapsed = (time.perf_counter() - start) * 1000
            sock.close()

            identity = MultiDeviceMonitor._parse_identity(data)
            return True, round(elapsed, 1), identity
        except Exception:
            return False, 0.0, None

    @staticmethod
    def _parse_identity(data: bytes) -> Optional[dict]:
        """Parse EtherNet/IP ListIdentity response."""
        if len(data) < 48:
            return None
        try:
            # Skip EIP header (24 bytes) + item count (2) + type (2) + len (2) + ver (2) + sockaddr (16)
            offset = 48
            if offset + 4 > len(data):
                return None
            vendor_id = struct.unpack_from("<H", data, offset)[0]
            device_type = struct.unpack_from("<H", data, offset + 2)[0]
            product_code = struct.unpack_from("<H", data, offset + 4)[0]
            # revision
            offset += 8
            if offset + 2 > len(data):
                return {"vendor_id": vendor_id}
            status = struct.unpack_from("<H", data, offset)[0]
            serial = struct.unpack_from("<I", data, offset + 2)[0]
            offset += 6
            if offset + 1 > len(data):
                return {"vendor_id": vendor_id}
            name_len = data[offset]
            offset += 1
            product_name = data[offset:offset + name_len].decode("utf-8", errors="replace").strip()

            return {
                "vendor_id": vendor_id,
                "device_type": device_type,
                "product_code": product_code,
                "product_name": product_name,
                "serial_number": serial,
                "vendor_name": "",
            }
        except Exception:
            return None

    # ── Export ────────────────────────────────────────────────────────────────

    def export_csv(self, filepath: str) -> Tuple[bool, str]:
        """Export trend data to CSV."""
        try:
            import csv
            with self._lock:
                data = list(self._trend_data)
                targets = list(self._targets)

            if not data:
                return False, "No data to export"

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                header = ["Timestamp", "Elapsed (s)"] + [t.display_name for t in targets]
                writer.writerow(header)

                start = data[0].timestamp if data else datetime.now()
                for pt in data:
                    elapsed = (pt.timestamp - start).total_seconds()
                    row = [pt.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], f"{elapsed:.1f}"]
                    for t in targets:
                        v = pt.values.get(t.ip)
                        row.append(f"{v:.1f}" if v is not None else "")
                    writer.writerow(row)

            return True, filepath
        except Exception as e:
            return False, str(e)
