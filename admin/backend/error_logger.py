"""
Centralized error logging system.
Stores up to 1000 log entries in memory (deque-based, thread-safe).
Note: logs are not persisted — they reset on service restart.
"""

import sys
import traceback
import logging
from datetime import datetime
from collections import deque
from threading import Lock
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ErrorLogger:
    def __init__(self, max_logs: int = 1000):
        self.logs = deque(maxlen=max_logs)
        self.lock = Lock()
        self.log_id_counter = 0

    def log_error(
        self,
        level: str,
        message: str,
        source: str = "backend",
        details: Optional[Dict] = None,
        exception: Optional[Exception] = None,
    ) -> int:
        """Store a log entry and forward to the Python logging system."""
        with self.lock:
            self.log_id_counter += 1

            entry = {
                "id": self.log_id_counter,
                "timestamp": datetime.now().isoformat(),
                "level": level.upper(),
                "message": message,
                "source": source,
                "details": details or {},
            }

            if exception:
                # Use the exception object directly — not sys.exc_info() —
                # so this works whether called inside or outside an except block.
                tb_str = "".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                )
                entry["exception"] = {
                    "type": type(exception).__name__,
                    "message": str(exception),
                    "traceback": tb_str or "No traceback available",
                }

            self.logs.append(entry)

            log_method = getattr(logger, level.lower(), logger.info)
            log_method("[%s] %s", source, message)

            return self.log_id_counter

    def get_logs(
        self,
        level: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Return filtered log entries, newest first."""
        with self.lock:
            # deque preserves insertion order (oldest → newest), reverse for newest first
            logs = list(reversed(self.logs))

            if level:
                logs = [e for e in logs if e["level"] == level.upper()]

            if source:
                logs = [e for e in logs if e["source"] == source]

            return logs[:limit]

    def get_stats(self) -> Dict:
        """Return log counts grouped by level and source."""
        with self.lock:
            by_level: Dict[str, int] = {}
            by_source: Dict[str, int] = {}

            for entry in self.logs:
                by_level[entry["level"]] = by_level.get(entry["level"], 0) + 1
                by_source[entry["source"]] = by_source.get(entry["source"], 0) + 1

            return {
                "total_logs": len(self.logs),
                "by_level": by_level,
                "by_source": by_source,
            }

    def clear_logs(self) -> None:
        """Clear all stored log entries and reset the ID counter."""
        with self.lock:
            self.logs.clear()
            self.log_id_counter = 0
            logger.info("Error logs cleared")


# Global singleton
error_logger = ErrorLogger()


# Convenience functions — thin wrappers around the global instance
def log_info(message: str, source: str = "backend", details: Optional[Dict] = None) -> int:
    return error_logger.log_error("INFO", message, source, details)


def log_warning(message: str, source: str = "backend", details: Optional[Dict] = None) -> int:
    return error_logger.log_error("WARNING", message, source, details)


def log_error(
    message: str,
    source: str = "backend",
    exception: Optional[Exception] = None,
    details: Optional[Dict] = None,
) -> int:
    return error_logger.log_error("ERROR", message, source, details, exception)


def log_critical(
    message: str,
    source: str = "backend",
    exception: Optional[Exception] = None,
    details: Optional[Dict] = None,
) -> int:
    return error_logger.log_error("CRITICAL", message, source, details, exception)
