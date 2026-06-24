"""
FAIA Error Monitoring System
Centralized error logging, monitoring, and alerting

NOTE: ErrorMonitor is stubbed - no SQLite, no background thread.
Project uses MySQL. SQLite file will never be created.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass
from enum import Enum
from contextlib import contextmanager


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    SYSTEM = "system"
    DATABASE = "database"
    MODEL = "model"
    API = "api"
    AUTHENTICATION = "authentication"
    CACHE = "cache"
    FILE_SYSTEM = "file_system"
    NETWORK = "network"
    SECURITY = "security"
    PERFORMANCE = "performance"


@dataclass
class ErrorEvent:
    """Represents an error event"""
    id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    service: str
    error_type: str
    message: str
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None


@dataclass
class SystemMetrics:
    """System performance metrics"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    disk_percent: float
    disk_free_gb: float
    active_connections: int
    response_time_avg: float
    error_rate: float


_severity_to_level = {
    ErrorSeverity.LOW: logging.DEBUG,
    ErrorSeverity.MEDIUM: logging.INFO,
    ErrorSeverity.HIGH: logging.WARNING,
    ErrorSeverity.CRITICAL: logging.ERROR,
}

_error_logger = logging.getLogger("faia.errors")


class ErrorMonitor:
    """Stub — no SQLite, no background thread. Project uses MySQL."""

    def __init__(self):
        self.monitoring_active = False
        self.recent_errors: deque = deque(maxlen=1000)
        self.system_metrics: deque = deque(maxlen=1000)

    def log_error(self, severity, category, service, error_type, message,
                  exception=None, context=None, user_id=None, session_id=None) -> str:
        level = _severity_to_level.get(severity, logging.WARNING)
        _error_logger.log(level, "[%s] %s: %s", service, error_type, message)
        return "%s_%d" % (service, int(time.time() * 1000))

    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        return {"period_hours": hours, "total_errors": 0, "errors_by_severity": {},
                "errors_by_category": {}, "errors_by_service": {}, "critical_errors": []}

    def get_system_health(self) -> Dict[str, Any]:
        return {"status": "healthy", "issues": [], "metrics": None,
                "recent_errors_count": 0, "monitoring_active": False}

    def resolve_error(self, error_id: str, resolution_notes: str = None) -> bool:
        return True

    def cleanup_old_data(self, days: int = 30):
        return {"deleted_errors": 0, "deleted_metrics": 0}

    def stop_monitoring(self):
        pass


# Global error monitor instance
error_monitor = ErrorMonitor()


# Convenience functions for easy usage
def log_error(severity: str, category: str, service: str, error_type: str,
              message: str, exception: Exception = None, **kwargs) -> str:
    return error_monitor.log_error(
        ErrorSeverity(severity),
        ErrorCategory(category),
        service,
        error_type,
        message,
        exception,
        **kwargs
    )


def log_critical_error(service: str, error_type: str, message: str,
                       exception: Exception = None, **kwargs) -> str:
    return log_error("critical", "system", service, error_type, message, exception, **kwargs)


def log_security_error(service: str, error_type: str, message: str,
                       user_id: str = None, **kwargs) -> str:
    return log_error("high", "security", service, error_type, message,
                     user_id=user_id, **kwargs)


def log_performance_warning(service: str, message: str, metrics: Dict = None, **kwargs) -> str:
    return log_error("medium", "performance", service, "performance_degradation",
                     message, context=metrics, **kwargs)


@contextmanager
def monitor_operation(service: str, operation: str,
                      severity: str = "medium", category: str = "system"):
    """Context manager to automatically log errors in operations"""
    try:
        yield
    except Exception as e:
        log_error(severity, category, service, operation, str(e), e)
        raise
