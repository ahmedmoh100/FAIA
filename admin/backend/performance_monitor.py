"""
Performance monitoring for the FAIA admin backend.
Tracks request metrics in memory (last 1000 requests) and exposes system resource stats.
Note: all data is in-memory and resets on service restart.
"""

import re
import logging
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

logger = logging.getLogger(__name__)

# Root of the drive this service is running on (works on Windows and Linux)
_DISK_ROOT = str(Path(__file__).anchor)

# Regex to normalize numeric path segments — prevents unbounded endpoint_stats growth
# e.g. /admin/users/123 → /admin/users/{id}
_PATH_PARAM_RE = re.compile(r'/\d+')


class PerformanceMonitor:
    def __init__(self):
        self.request_times: deque = deque(maxlen=1000)
        self.error_count: int = 0
        self.total_requests: int = 0
        self.lock = Lock()
        self.start_time = datetime.now()
        self.endpoint_stats: Dict[str, Dict] = {}

    def record_request(self, duration: float, status_code: int, endpoint: Optional[str] = None) -> None:
        """Record a single request's duration and status."""
        if endpoint:
            endpoint = _PATH_PARAM_RE.sub("/{id}", endpoint)

        with self.lock:
            self.request_times.append({
                "timestamp": datetime.now(),
                "duration": duration,
                "status_code": status_code,
                "endpoint": endpoint,
            })
            self.total_requests += 1
            if status_code >= 400:
                self.error_count += 1

            if endpoint:
                stats = self.endpoint_stats.setdefault(endpoint, {"count": 0, "total_duration": 0.0, "errors": 0})
                stats["count"] += 1
                stats["total_duration"] += duration
                if status_code >= 400:
                    stats["errors"] += 1

    def get_stats(self) -> Dict:
        """Return current performance statistics including system resource usage."""
        # Collect system metrics before acquiring the lock.
        # psutil.cpu_percent(interval=0.1) blocks for 100ms — holding the lock
        # during that time would stall concurrent record_request() calls.
        system_metrics = self._get_system_metrics()

        with self.lock:
            now = datetime.now()
            one_minute_ago = now - timedelta(minutes=1)
            recent = [r for r in self.request_times if r["timestamp"] > one_minute_ago]

            requests_per_min = len(recent)
            if recent:
                avg_response_time = sum(r["duration"] for r in recent) / len(recent)
                error_requests = sum(1 for r in recent if r["status_code"] >= 400)
                error_rate = (error_requests / len(recent)) * 100
                slowest_endpoint = max(recent, key=lambda r: r["duration"]).get("endpoint")
            else:
                avg_response_time = 0.0
                error_rate = 0.0
                slowest_endpoint = None

            uptime_seconds = (now - self.start_time).total_seconds()

            return {
                "requests_per_min": requests_per_min,
                "avg_response_time": round(avg_response_time * 1000, 2),  # ms
                "error_rate": round(error_rate, 2),
                "total_requests": self.total_requests,
                "total_errors": self.error_count,
                "uptime": self._format_uptime(uptime_seconds),
                "uptime_seconds": int(uptime_seconds),
                "slowest_endpoint": slowest_endpoint,
                **system_metrics,
            }

    def _get_system_metrics(self) -> Dict:
        """Return CPU, memory, disk, and network stats. Returns zeros if psutil unavailable."""
        empty = {
            "cpu_percent": 0, "memory_percent": 0,
            "memory_used_mb": 0, "memory_total_mb": 0,
            "disk_percent": 0, "disk_used_gb": 0, "disk_total_gb": 0,
            "network_sent_mb": 0, "network_recv_mb": 0,
        }
        if not HAS_PSUTIL:
            return empty
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(_DISK_ROOT)
            net = psutil.net_io_counters()
            return {
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(mem.percent, 2),
                "memory_used_mb": round(mem.used / (1024 ** 2), 2),
                "memory_total_mb": round(mem.total / (1024 ** 2), 2),
                "disk_percent": round(disk.percent, 2),
                "disk_used_gb": round(disk.used / (1024 ** 3), 2),
                "disk_total_gb": round(disk.total / (1024 ** 3), 2),
                "network_sent_mb": round(net.bytes_sent / (1024 ** 2), 2),
                "network_recv_mb": round(net.bytes_recv / (1024 ** 2), 2),
            }
        except Exception as e:
            logger.error("Failed to read system metrics: %s", e)
            return empty

    def get_endpoint_stats(self) -> List[Dict]:
        """Return per-endpoint request counts and average response times, sorted by count."""
        with self.lock:
            stats = []
            for endpoint, data in self.endpoint_stats.items():
                if data["count"] > 0:
                    stats.append({
                        "endpoint": endpoint,
                        "count": data["count"],
                        "avg_duration_ms": round((data["total_duration"] / data["count"]) * 1000, 2),
                        "error_rate": round((data["errors"] / data["count"]) * 100, 2),
                        "total_errors": data["errors"],
                    })
            return sorted(stats, key=lambda x: x["count"], reverse=True)

    def _format_uptime(self, seconds: float) -> str:
        """Format a duration in seconds as a human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def reset_stats(self) -> None:
        """Reset all tracked metrics."""
        with self.lock:
            self.request_times.clear()
            self.error_count = 0
            self.total_requests = 0
            self.endpoint_stats.clear()
            self.start_time = datetime.now()
            logger.info("Performance statistics reset")


# Global singleton
performance_monitor = PerformanceMonitor()
