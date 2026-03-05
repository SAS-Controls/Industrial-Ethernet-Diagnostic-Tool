"""
SAS Network Diagnostic Tool — Link Quality Analyzer Engine

Tests a target device with progressively larger ICMP payloads and rapid-fire
bursts to detect:
  - MTU/fragmentation issues (common with EtherNet/IP jumbo frame configs)
  - Half-duplex or duplex mismatch (latency spikes under load)
  - Marginal cable or connector (higher loss at larger frames)
  - General link stability before commissioning

Each test result is a LinkSizeResult. An LQAnalysis holds all results plus
plain-English findings with specific action steps.
"""

import logging
import math
import platform
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Tuple

logger = logging.getLogger(__name__)

# Payload sizes to test (bytes) — covers typical industrial scenarios
# 28 = minimum ping, 1472 = maximum unfragmented on standard 1500 MTU
PAYLOAD_SIZES = [28, 64, 128, 256, 512, 1024, 1280, 1472]

# Rapid-fire burst: tests jitter under load at small frame size
BURST_COUNT = 20
BURST_SIZE  = 64


@dataclass
class LinkSizeResult:
    """Ping result for a single payload size."""
    payload_bytes: int
    sent: int = 0
    received: int = 0
    loss_pct: float = 0.0
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    jitter_ms: float = 0.0   # max - min (simple jitter for display)
    timed_out: bool = False   # True if ALL packets were lost (not just some)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.received > 0 and self.loss_pct < 50


@dataclass
class BurstResult:
    """Rapid-fire burst test result at 64-byte payload."""
    sent: int = 0
    received: int = 0
    loss_pct: float = 0.0
    avg_ms: float = 0.0
    jitter_ms: float = 0.0   # std dev across burst pings
    max_ms: float = 0.0
    min_ms: float = 0.0


@dataclass
class LQFinding:
    """A diagnostic finding from the link quality test."""
    title: str
    severity: str          # "ok", "warning", "critical"
    detail: str


@dataclass
class LQAnalysis:
    """Complete result of a link quality test run."""
    target_ip: str
    timestamp: float = 0.0
    cancelled: bool = False
    error: str = ""

    size_results: List[LinkSizeResult] = field(default_factory=list)
    burst_result: Optional[BurstResult] = None

    findings: List[LQFinding] = field(default_factory=list)
    health_score: int = 100

    # Derived convenience values
    mtu_limit: Optional[int] = None        # Largest payload that got through
    fragmentation_threshold: Optional[int] = None  # First size where loss started


class LinkQualityEngine:
    """
    Runs the link quality test sequence against a target IP.
    Results are delivered via callbacks to keep the UI responsive.
    """

    def __init__(self):
        self._cancel_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self,
              target_ip: str,
              on_progress: Callable[[str, float], None],
              on_size_result: Callable[[LinkSizeResult], None],
              on_complete: Callable[[LQAnalysis], None]):
        """Start the link quality test in a background thread."""
        self._cancel_flag.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(target_ip, on_progress, on_size_result, on_complete),
            daemon=True,
        )
        self._thread.start()

    def cancel(self):
        self._cancel_flag.set()

    def _run(self, target_ip, on_progress, on_size_result, on_complete):
        analysis = LQAnalysis(target_ip=target_ip, timestamp=time.time())

        total_steps = len(PAYLOAD_SIZES) + 1   # sizes + burst
        completed   = 0

        try:
            # ── Step 1: Progressive payload size tests ──────────────────────
            for size in PAYLOAD_SIZES:
                if self._cancel_flag.is_set():
                    analysis.cancelled = True
                    break

                on_progress(f"Testing {size}-byte payload…", completed / total_steps)
                result = self._ping_with_size(target_ip, size, count=5)
                analysis.size_results.append(result)
                on_size_result(result)
                completed += 1
                time.sleep(0.1)

            # ── Step 2: Burst test (load jitter) ────────────────────────────
            if not self._cancel_flag.is_set():
                on_progress(f"Burst test — {BURST_COUNT} rapid pings at {BURST_SIZE}B…",
                             completed / total_steps)
                analysis.burst_result = self._burst_test(target_ip, BURST_SIZE, BURST_COUNT)
                completed += 1

            if not analysis.cancelled:
                on_progress("Analyzing results…", 0.95)
                _analyze(analysis)

        except Exception as e:
            logger.error(f"LinkQualityEngine error: {e}", exc_info=True)
            analysis.error = str(e)

        on_progress("Complete", 1.0)
        on_complete(analysis)

    # ── Platform ping helpers ────────────────────────────────────────────────

    def _ping_with_size(self, ip: str, size: int, count: int = 5) -> LinkSizeResult:
        """Run `ping` with the given payload size and parse output."""
        result = LinkSizeResult(payload_bytes=size, sent=count)

        is_win = platform.system() == "Windows"
        if is_win:
            # Windows: ping -n count -l size -w timeout_ms ip
            cmd = ["ping", "-n", str(count), "-l", str(size), "-w", "2000", ip]
        else:
            # Linux/macOS: ping -c count -s size -W timeout ip
            cmd = ["ping", "-c", str(count), "-s", str(size), "-W", "2", ip]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0,
            )
            output = proc.stdout + proc.stderr
            self._parse_ping_output(output, result, is_win)
        except subprocess.TimeoutExpired:
            result.timed_out = True
            result.loss_pct  = 100.0
            result.error     = "Timed out"
        except Exception as e:
            result.error = str(e)

        return result

    @staticmethod
    def _parse_ping_output(output: str, result: LinkSizeResult, is_win: bool):
        """Parse platform ping output into a LinkSizeResult."""
        if is_win:
            # "Packets: Sent = 5, Received = 4, Lost = 1 (20% loss)"
            m = re.search(r"Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+)", output, re.I)
            if m:
                result.sent     = int(m.group(1))
                result.received = int(m.group(2))
                result.loss_pct = (result.sent - result.received) / result.sent * 100

            # "Minimum = 1ms, Maximum = 3ms, Average = 2ms"
            m2 = re.search(r"Minimum\s*=\s*(\d+)ms.*Maximum\s*=\s*(\d+)ms.*Average\s*=\s*(\d+)ms",
                           output, re.I)
            if m2:
                result.min_ms    = float(m2.group(1))
                result.max_ms    = float(m2.group(2))
                result.avg_ms    = float(m2.group(3))
                result.jitter_ms = result.max_ms - result.min_ms
        else:
            # "5 packets transmitted, 4 received, 20% packet loss"
            m = re.search(r"(\d+) packets transmitted,\s*(\d+) received", output)
            if m:
                result.sent     = int(m.group(1))
                result.received = int(m.group(2))
                result.loss_pct = (result.sent - result.received) / result.sent * 100

            # "rtt min/avg/max/mdev = 0.456/0.789/1.234/0.200 ms"
            m2 = re.search(r"min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", output)
            if m2:
                result.min_ms    = float(m2.group(1))
                result.avg_ms    = float(m2.group(2))
                result.max_ms    = float(m2.group(3))
                result.jitter_ms = result.max_ms - result.min_ms

        if result.received == 0:
            result.timed_out = True

    def _burst_test(self, ip: str, size: int, count: int) -> BurstResult:
        """Run rapid-fire pings and calculate jitter."""
        is_win = platform.system() == "Windows"

        if is_win:
            cmd = ["ping", "-n", str(count), "-l", str(size), "-w", "2000", ip]
        else:
            cmd = ["ping", "-c", str(count), "-i", "0.1", "-s", str(size), "-W", "2", ip]

        result = BurstResult(sent=count)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0,
            )
            output = proc.stdout + proc.stderr

            # Parse individual RTT values for std dev jitter
            if is_win:
                times = [float(m) for m in re.findall(r"time[<=](\d+)ms", output)]
                m_sum = re.search(r"Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+)", output, re.I)
                if m_sum:
                    result.received = int(m_sum.group(2))
                    result.loss_pct = (count - result.received) / count * 100
                m_rtt = re.search(r"Minimum\s*=\s*(\d+)ms.*Maximum\s*=\s*(\d+)ms.*Average\s*=\s*(\d+)ms",
                                   output, re.I)
                if m_rtt:
                    result.min_ms = float(m_rtt.group(1))
                    result.max_ms = float(m_rtt.group(2))
                    result.avg_ms = float(m_rtt.group(3))
            else:
                times = [float(m) for m in re.findall(r"time=([\d.]+)\s*ms", output)]
                m_sum = re.search(r"(\d+) packets transmitted,\s*(\d+) received", output)
                if m_sum:
                    result.received = int(m_sum.group(2))
                    result.loss_pct = (count - result.received) / count * 100
                m_rtt = re.search(r"min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", output)
                if m_rtt:
                    result.min_ms = float(m_rtt.group(1))
                    result.avg_ms = float(m_rtt.group(2))
                    result.max_ms = float(m_rtt.group(3))

            # Std-dev jitter from individual times
            if len(times) >= 2:
                mean = sum(times) / len(times)
                variance = sum((t - mean) ** 2 for t in times) / len(times)
                result.jitter_ms = math.sqrt(variance)

        except Exception as e:
            logger.warning(f"Burst test error: {e}")

        return result


# ── Analysis ─────────────────────────────────────────────────────────────────

def _analyze(analysis: LQAnalysis):
    """Generate plain-English findings from test results."""
    results = analysis.size_results
    score   = 100

    if not results:
        return

    # ── Find MTU limit & fragmentation threshold ──────────────────────────
    last_ok   = None
    first_bad = None
    for r in results:
        if r.ok:
            last_ok = r.payload_bytes
        elif first_bad is None:
            first_bad = r.payload_bytes

    analysis.mtu_limit             = last_ok
    analysis.fragmentation_threshold = first_bad

    # ── Reachability ──────────────────────────────────────────────────────
    if not any(r.ok for r in results):
        score -= 60
        analysis.findings.append(LQFinding(
            title="🔴 Device Unreachable",
            severity="critical",
            detail=(
                f"No ping responses from {analysis.target_ip} at any payload size.\n\n"
                "Check:\n"
                "• Is the device powered on and on this network segment?\n"
                "• Does the device's firewall block ICMP (ping)?\n"
                "• Is the IP address correct?\n"
                "• Is the PC on the same subnet?"
            ),
        ))
        analysis.health_score = max(0, score)
        return

    # ── Baseline latency at smallest size ────────────────────────────────
    small = next((r for r in results if r.ok), None)
    if small:
        if small.avg_ms > 100:
            score -= 20
            analysis.findings.append(LQFinding(
                title="⚠ High Baseline Latency",
                severity="warning",
                detail=(
                    f"Response time is {small.avg_ms:.1f}ms even at a 28-byte payload.\n\n"
                    "On a local industrial Ethernet segment, latency should be <2ms. "
                    "Values above 10ms usually mean:\n"
                    "• A slow processing device (embedded web server overloaded)\n"
                    "• Traffic passing through multiple hops or routers\n"
                    "• Device CPU heavily loaded (excessive polling)\n\n"
                    f"Tip: Use 'tracert {analysis.target_ip}' to count network hops."
                ),
            ))
        elif small.avg_ms > 20:
            score -= 5
            analysis.findings.append(LQFinding(
                title="⚠ Elevated Baseline Latency",
                severity="warning",
                detail=(
                    f"Baseline ping is {small.avg_ms:.1f}ms — acceptable but worth noting.\n"
                    "On a direct Ethernet connection this should typically be under 5ms.\n"
                    "Device may be CPU-limited or on a multi-hop path."
                ),
            ))
        else:
            analysis.findings.append(LQFinding(
                title="✅ Baseline Latency",
                severity="ok",
                detail=f"Baseline ping at 28 bytes: {small.avg_ms:.1f}ms — excellent.",
            ))

    # ── Fragmentation / MTU ───────────────────────────────────────────────
    if first_bad is not None:
        score -= 25
        analysis.findings.append(LQFinding(
            title=f"⚠ Packet Loss Above {last_ok or '?'}-Byte Payload",
            severity="warning",
            detail=(
                f"Packets start failing at {first_bad}-byte payload size.\n\n"
                "This is a strong indicator of an MTU mismatch or fragmentation problem:\n\n"
                "• Standard Ethernet MTU = 1500 bytes → max unfragmented payload = 1472 bytes\n"
                "• If loss starts below 1472: a link on the path has a smaller MTU "
                "(misconfigured jumbo frame, VPN overhead, or PPPoE link)\n"
                "• EtherNet/IP large packets (forward open with large connection size) will "
                "be affected by this\n\n"
                "Fix: Run 'ping -f -l 1472 target' to test fragmentation. "
                "Check switch/router MTU settings on all links between source and target."
            ),
        ))
    else:
        analysis.findings.append(LQFinding(
            title="✅ No Fragmentation Issues",
            severity="ok",
            detail=(
                "All payload sizes from 28 to 1472 bytes received successfully.\n"
                "MTU is at least 1500 bytes end-to-end — standard Ethernet frames "
                "will not be fragmented on this path."
            ),
        ))

    # ── Latency increase with frame size (cable/duplex degradation) ───────
    ok_results = [r for r in results if r.ok]
    if len(ok_results) >= 3:
        first_avg = ok_results[0].avg_ms
        last_avg  = ok_results[-1].avg_ms
        latency_rise = last_avg - first_avg

        if latency_rise > 50:
            score -= 15
            analysis.findings.append(LQFinding(
                title="⚠ Large Latency Increase with Frame Size",
                severity="warning",
                detail=(
                    f"Latency jumps from {first_avg:.1f}ms (small frames) to "
                    f"{last_avg:.1f}ms (large frames) — a {latency_rise:.0f}ms increase.\n\n"
                    "A large increase with frame size can indicate:\n"
                    "• Half-duplex mismatch — devices in half-duplex collide more under load\n"
                    "• A congested switch port struggling with larger frames\n"
                    "• Marginal cable that retransmits at Layer 1 under load\n\n"
                    "Action: Check switch port for input errors, CRC errors, or collisions. "
                    "Verify both ends are set to full-duplex."
                ),
            ))
        elif latency_rise > 15:
            analysis.findings.append(LQFinding(
                title="ℹ Moderate Latency Increase with Frame Size",
                severity="ok",
                detail=(
                    f"Latency rises {latency_rise:.0f}ms from smallest to largest payload. "
                    "This is within normal range for most industrial Ethernet devices."
                ),
            ))
        else:
            analysis.findings.append(LQFinding(
                title="✅ Consistent Latency Across Frame Sizes",
                severity="ok",
                detail=(
                    f"Latency variation across frame sizes is only {latency_rise:.1f}ms. "
                    "Link appears stable and not congested."
                ),
            ))

    # ── Packet loss at mid-sizes (marginal cable) ─────────────────────────
    mid_loss = [r for r in results if r.ok and 128 <= r.payload_bytes <= 1024 and r.loss_pct > 0]
    if mid_loss:
        worst = max(mid_loss, key=lambda r: r.loss_pct)
        score -= 15
        analysis.findings.append(LQFinding(
            title=f"⚠ Intermittent Packet Loss ({worst.payload_bytes}-byte frames)",
            severity="warning",
            detail=(
                f"Packet loss of {worst.loss_pct:.0f}% detected at {worst.payload_bytes}-byte payload.\n\n"
                "Intermittent loss at mid-sized frames is typically caused by:\n"
                "• Marginal cable (near the limit of its specification)\n"
                "• Failing connector — check both ends and any patch panel connections\n"
                "• Mismatched SFP modules (speed/wavelength mismatch in fiber runs)\n"
                "• Switch port error — check CRC counters on the connected port\n\n"
                "Start by replacing the patch cable and retesting."
            ),
        ))

    # ── Burst jitter (duplex/congestion detection) ────────────────────────
    br = analysis.burst_result
    if br and br.received > 0:
        if br.jitter_ms > 30:
            score -= 20
            analysis.findings.append(LQFinding(
                title="🔴 Very High Jitter Under Load — Likely Duplex Mismatch",
                severity="critical",
                detail=(
                    f"Jitter under rapid-fire burst: {br.jitter_ms:.1f}ms (σ)  "
                    f"— range {br.min_ms:.1f}ms to {br.max_ms:.1f}ms.\n\n"
                    "Jitter above 20ms during a burst test is the classic signature of a "
                    "half-duplex / full-duplex mismatch:\n"
                    "• One end is full-duplex, the other is half-duplex\n"
                    "• The half-duplex side detects collisions and backs off, causing large "
                    "  latency spikes exactly under load\n"
                    "• This is invisible on light traffic (single ping looks fine) but "
                    "  causes random timeouts under real I/O load\n\n"
                    "Action:\n"
                    "1. Log into the switch and check the port speed/duplex setting\n"
                    "2. Check the device's NIC settings (if configurable)\n"
                    "3. Force both ends to the same setting (e.g. 100Mbps full-duplex) "
                    "   rather than using auto-negotiate"
                ),
            ))
        elif br.jitter_ms > 10:
            score -= 10
            analysis.findings.append(LQFinding(
                title="⚠ Elevated Jitter Under Load",
                severity="warning",
                detail=(
                    f"Burst jitter: {br.jitter_ms:.1f}ms — range {br.min_ms:.1f}ms "
                    f"to {br.max_ms:.1f}ms.\n\n"
                    "Moderate jitter under load may indicate link congestion or a "
                    "marginal connection. Monitor in context — a busy network segment "
                    "may show some jitter naturally. If devices are showing I/O timeouts, "
                    "this is worth investigating further."
                ),
            ))
        else:
            analysis.findings.append(LQFinding(
                title="✅ Stable Under Load",
                severity="ok",
                detail=(
                    f"Burst jitter: {br.jitter_ms:.1f}ms — link is stable under rapid traffic. "
                    "No duplex mismatch or congestion detected."
                ),
            ))

    analysis.health_score = max(0, min(100, score))
