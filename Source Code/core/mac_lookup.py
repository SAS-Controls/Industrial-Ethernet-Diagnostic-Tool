"""
SAS Network Diagnostic Tool — MAC Address Lookup Engine
Batch MAC address lookup with local OUI database + web fallback.
"""

import logging
import re
import threading
import urllib.request
import urllib.error
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict

from core.mac_vendors import lookup_vendor

logger = logging.getLogger(__name__)

_API_URL = "https://api.maclookup.app/v2/macs/{oui}"
_MIN_INTERVAL = 0.55


@dataclass
class MACResult:
    """Result of a single MAC address lookup."""
    mac_address: str
    mac_normalized: str = ""
    vendor: str = ""
    source: str = ""      # "local", "online", "not found"
    oui: str = ""
    category: str = ""
    error: str = ""

    @property
    def mac_display(self) -> str:
        """Format as XX:XX:XX:XX:XX:XX."""
        m = self.mac_normalized
        if len(m) == 12:
            return ":".join(m[i:i+2] for i in range(0, 12, 2))
        return self.mac_address

    @property
    def oui_display(self) -> str:
        m = self.mac_normalized
        if len(m) >= 6:
            return ":".join(m[i:i+2] for i in range(0, 6, 2))
        return ""


def normalize_mac(mac: str) -> str:
    """Strip a MAC to uppercase hex only."""
    return re.sub(r'[^0-9a-fA-F]', '', mac).upper()


def validate_mac(mac_normalized: str) -> bool:
    """Check if normalized MAC is valid (6-12 hex chars)."""
    return bool(re.match(r'^[0-9A-F]{6,12}$', mac_normalized))


def _online_lookup(oui: str) -> Optional[str]:
    """Query maclookup.app for a vendor name."""
    try:
        url = _API_URL.format(oui=oui)
        req = urllib.request.Request(url, headers={"User-Agent": "SAS-NetDiag/3.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("success") and data.get("found"):
                return data.get("company", "")
    except Exception as e:
        logger.debug(f"Online MAC lookup failed for {oui}: {e}")
    return None


def lookup_single(mac_raw: str) -> MACResult:
    """Look up a single MAC address — local first, then online."""
    mac_norm = normalize_mac(mac_raw)

    result = MACResult(mac_address=mac_raw, mac_normalized=mac_norm)

    if not validate_mac(mac_norm):
        result.error = "Invalid MAC address format"
        result.source = "error"
        return result

    result.oui = mac_norm[:6]

    # Try local database first
    local = lookup_vendor(mac_raw)
    if local and local != "Unknown":
        result.vendor = local
        result.source = "local"
        return result

    # Try online
    online = _online_lookup(result.oui)
    if online:
        result.vendor = online
        result.source = "online"
        return result

    result.vendor = "Unknown"
    result.source = "not found"
    return result


def lookup_batch(mac_list: List[str],
                 on_result: Optional[Callable[[MACResult], None]] = None,
                 on_complete: Optional[Callable[[List[MACResult]], None]] = None):
    """Look up a list of MACs in a background thread."""
    def _run():
        results = []
        for mac in mac_list:
            r = lookup_single(mac.strip())
            results.append(r)
            if on_result:
                try:
                    on_result(r)
                except Exception:
                    pass
            # Rate limit for online lookups
            if r.source == "online":
                time.sleep(_MIN_INTERVAL)
        if on_complete:
            try:
                on_complete(results)
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
