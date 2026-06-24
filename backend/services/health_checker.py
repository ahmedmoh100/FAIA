"""
FAIA Health Check System
Comprehensive health monitoring for all services
"""

import asyncio
import aiohttp
import time
import psutil
from collections import deque
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

from error_monitor import error_monitor, ErrorSeverity, ErrorCategory

logger = logging.getLogger(__name__)

@dataclass
class ServiceHealth:
    """Health status of a service"""
    name: str
    url: str
    status: str  # healthy, warning, critical, down
    response_time: float
    last_check: datetime
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

@dataclass
class SystemHealth:
    """Overall system health"""
    status: str  # healthy, warning, critical
    services: List[ServiceHealth]
    system_metrics: Dict[str, Any]
    issues: List[str]
    last_updated: datetime

class HealthChecker:
    """Comprehensive health checking system"""
    
    def __init__(self):
        self.services = {
            'backend': 'http://localhost:8000/health',
            'admin_backend': 'http://localhost:8001/admin/health',
            'web_frontend': 'http://localhost:8080/health',
            'admin_frontend': 'http://localhost:5500',
            'qwen_model': 'http://localhost:8000/model/status'
        }
        
        self.health_history: deque = deque(maxlen=1000)
        
        # Health check intervals (seconds)
        self.check_intervals = {
            'fast': 30,    # Critical services
            'normal': 60,  # Regular services
            'slow': 300    # Less critical services
        }
        
        # Response time thresholds (seconds)
        self.response_thresholds = {
            'good': 1.0,
            'warning': 3.0,
            'critical': 10.0
        }
    
    async def check_service_health(self, name: str, url: str, timeout: int = 10) -> ServiceHealth:
        """Check health of a single service"""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(url) as response:
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        try:
                            data = await response.json()
                            status = self._determine_service_status(response_time, data)
                            
                            return ServiceHealth(
                                name=name,
                                url=url,
                                status=status,
                                response_time=response_time,
                                last_check=datetime.now(),
                                details=data
                            )
                        except Exception:
                            # Service responded but not with JSON
                            status = self._determine_service_status(response_time, None)
                            return ServiceHealth(
                                name=name,
                                url=url,
                                status=status,
                                response_time=response_time,
                                last_check=datetime.now()
                            )
                    else:
                        error_message = f"HTTP {response.status}"
                        error_monitor.log_error(
                            ErrorSeverity.HIGH,
                            ErrorCategory.API,
                            name,
                            "health_check_failed",
                            f"Service returned HTTP {response.status}",
                            context={'url': url, 'status_code': response.status}
                        )
                        
                        return ServiceHealth(
                            name=name,
                            url=url,
                            status='critical',
                            response_time=response_time,
                            last_check=datetime.now(),
                            error_message=error_message
                        )
        
        except asyncio.TimeoutError:
            error_message = f"Timeout after {timeout}s"
            error_monitor.log_error(
                ErrorSeverity.HIGH,
                ErrorCategory.NETWORK,
                name,
                "health_check_timeout",
                f"Service health check timed out after {timeout}s",
                context={'url': url, 'timeout': timeout}
            )
            
            return ServiceHealth(
                name=name,
                url=url,
                status='down',
                response_time=timeout,
                last_check=datetime.now(),
                error_message=error_message
            )
        
        except asyncio.CancelledError:
            raise
        except Exception as e:
            error_message = str(e)
            error_monitor.log_error(
                ErrorSeverity.HIGH,
                ErrorCategory.NETWORK,
                name,
                "health_check_error",
                f"Health check failed: {str(e)}",
                exception=e,
                context={'url': url}
            )
            
            return ServiceHealth(
                name=name,
                url=url,
                status='down',
                response_time=time.time() - start_time,
                last_check=datetime.now(),
                error_message=error_message
            )
    
    def _determine_service_status(self, response_time: float, data: Dict = None) -> str:
        """Determine service status based on response time and data"""
        # Check response time
        if response_time > self.response_thresholds['critical']:
            return 'critical'
        elif response_time > self.response_thresholds['warning']:
            return 'warning'
        
        # Check service-specific health indicators
        if data:
            # Model service specific checks
            if 'model_service' in data or 'qwen_model' in data:
                model_info = data.get('qwen_model', data.get('model_service', {}))
                model_loaded = model_info.get('qwen_loaded', model_info.get('model_loaded', False))
                loading_error = model_info.get('qwen_error', model_info.get('loading_error'))
                
                if not model_loaded:
                    return 'warning'
                if loading_error:
                    return 'critical'
            
            # Database checks
            if 'database' in data:
                db_info = data['database']
                if not db_info.get('connected', True):
                    return 'critical'
            
            # Memory checks
            if 'memory_percent' in data:
                memory_percent = data['memory_percent']
                if memory_percent > 90:
                    return 'critical'
                elif memory_percent > 80:
                    return 'warning'
            
            # CPU checks
            if 'cpu_percent' in data:
                cpu_percent = data['cpu_percent']
                if cpu_percent > 90:
                    return 'critical'
                elif cpu_percent > 80:
                    return 'warning'
        
        return 'healthy'
    
    async def check_all_services(self) -> SystemHealth:
        """Check health of all services"""
        service_checks = []
        
        # Check all services concurrently
        for name, url in self.services.items():
            service_checks.append(self.check_service_health(name, url))
        
        service_results = await asyncio.gather(*service_checks, return_exceptions=True)
        
        # Process results
        services = []
        for result in service_results:
            if isinstance(result, ServiceHealth):
                services.append(result)
            else:
                # Handle exceptions
                logger.error("Health check failed: %s", result)
        
        # Get system metrics
        system_metrics = self._get_system_metrics()
        
        # Determine overall system status
        overall_status, issues = self._determine_overall_status(services, system_metrics)
        
        system_health = SystemHealth(
            status=overall_status,
            services=services,
            system_metrics=system_metrics,
            issues=issues,
            last_updated=datetime.now()
        )
        
        # Store in history (deque handles maxlen automatically)
        self.health_history.append(system_health)
        
        return system_health
    
    def _get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        try:
            # CPU — interval=None is non-blocking (returns since last call)
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()

            # Disk — use '.' (current directory) for cross-platform compatibility
            disk = psutil.disk_usage('.')
            
            # Network
            network = psutil.net_io_counters()
            
            # Process count
            process_count = len(psutil.pids())
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': round(memory.used / (1024**3), 2),
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'disk_percent': disk.percent,
                'disk_free_gb': round(disk.free / (1024**3), 2),
                'network_bytes_sent': network.bytes_sent,
                'network_bytes_recv': network.bytes_recv,
                'process_count': process_count,
                'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat()
            }
        
        except Exception as e:
            error_monitor.log_error(
                ErrorSeverity.MEDIUM,
                ErrorCategory.SYSTEM,
                "health_checker",
                "metrics_collection_failed",
                f"Failed to collect system metrics: {str(e)}",
                exception=e
            )
            return {'error': 'Failed to collect system metrics'}
    
    def _determine_overall_status(self, services: List[ServiceHealth],
                                 system_metrics: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Determine overall system status and issues"""
        issues = []
        critical_services = 0
        warning_services = 0
        down_services = 0
        
        # Check service statuses
        for service in services:
            if service.status == 'critical':
                critical_services += 1
                issues.append(f"{service.name} is in critical state")
            elif service.status == 'warning':
                warning_services += 1
                issues.append(f"{service.name} has warnings")
            elif service.status == 'down':
                down_services += 1
                issues.append(f"{service.name} is down")
        
        # Check system metrics
        if 'cpu_percent' in system_metrics:
            cpu = system_metrics['cpu_percent']
            if cpu > 90:
                issues.append(f"High CPU usage: {cpu:.1f}%")
            elif cpu > 80:
                issues.append(f"Elevated CPU usage: {cpu:.1f}%")
        
        if 'memory_percent' in system_metrics:
            memory = system_metrics['memory_percent']
            if memory > 90:
                issues.append(f"Critical memory usage: {memory:.1f}%")
            elif memory > 80:
                issues.append(f"High memory usage: {memory:.1f}%")
        
        if 'disk_percent' in system_metrics:
            disk = system_metrics['disk_percent']
            if disk > 95:
                issues.append(f"Critical disk usage: {disk:.1f}%")
            elif disk > 85:
                issues.append(f"High disk usage: {disk:.1f}%")
        
        # Determine overall status
        if down_services > 0 or critical_services > 1:
            return 'critical', issues
        elif critical_services > 0 or warning_services > 2:
            return 'warning', issues
        elif warning_services > 0 or len(issues) > 0:
            return 'warning', issues
        else:
            return 'healthy', issues
    
    def get_service_uptime(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """Calculate service uptime for the last N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter health checks for this service and time period
        relevant_checks = []
        for health in self.health_history:
            if health.last_updated > cutoff_time:
                for service in health.services:
                    if service.name == service_name:
                        relevant_checks.append(service)
                        break
        
        if not relevant_checks:
            return {'error': 'No health check data available'}
        
        # Calculate uptime
        total_checks = len(relevant_checks)
        healthy_checks = sum(1 for check in relevant_checks if check.status == 'healthy')
        warning_checks = sum(1 for check in relevant_checks if check.status == 'warning')
        critical_checks = sum(1 for check in relevant_checks if check.status == 'critical')
        down_checks = sum(1 for check in relevant_checks if check.status == 'down')
        
        uptime_percentage = (healthy_checks + warning_checks) / total_checks * 100
        
        # Calculate average response time
        response_times = [check.response_time for check in relevant_checks]
        avg_response_time = sum(response_times) / len(response_times)
        
        return {
            'service': service_name,
            'period_hours': hours,
            'total_checks': total_checks,
            'uptime_percentage': round(uptime_percentage, 2),
            'healthy_checks': healthy_checks,
            'warning_checks': warning_checks,
            'critical_checks': critical_checks,
            'down_checks': down_checks,
            'avg_response_time': round(avg_response_time, 3),
            'last_check': relevant_checks[-1].last_check.isoformat() if relevant_checks else None
        }
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary"""
        if not self.health_history:
            return {'error': 'No health data available'}
        
        latest_health = self.health_history[-1]
        
        # Service summaries
        service_summaries = {}
        for service in latest_health.services:
            service_summaries[service.name] = {
                'status': service.status,
                'response_time': service.response_time,
                'last_check': service.last_check.isoformat(),
                'error_message': service.error_message
            }
        
        # System health trends (last 10 checks)
        recent_checks = self.health_history[-10:]
        status_trend = [check.status for check in recent_checks]
        
        return {
            'overall_status': latest_health.status,
            'issues': latest_health.issues,
            'services': service_summaries,
            'system_metrics': latest_health.system_metrics,
            'status_trend': status_trend,
            'last_updated': latest_health.last_updated.isoformat(),
            'total_health_checks': len(self.health_history)
        }

# Global health checker instance
health_checker = HealthChecker()

# Convenience functions
async def check_system_health() -> Dict[str, Any]:
    """Check overall system health"""
    try:
        health = await health_checker.check_all_services()
        return asdict(health)
    except Exception as e:
        error_monitor.log_error(
            ErrorSeverity.HIGH,
            ErrorCategory.SYSTEM,
            "health_checker",
            "system_health_check_failed",
            f"Failed to check system health: {str(e)}",
            exception=e
        )
        return {'error': 'Failed to check system health', 'details': str(e)}

async def check_service_health(service_name: str) -> Dict[str, Any]:
    """Check health of a specific service"""
    try:
        if service_name not in health_checker.services:
            return {'error': f'Unknown service: {service_name}'}
        
        url = health_checker.services[service_name]
        health = await health_checker.check_service_health(service_name, url)
        return asdict(health)
    
    except Exception as e:
        error_monitor.log_error(
            ErrorSeverity.MEDIUM,
            ErrorCategory.SYSTEM,
            "health_checker",
            "service_health_check_failed",
            f"Failed to check {service_name} health: {str(e)}",
            exception=e
        )
        return {'error': f'Failed to check {service_name} health', 'details': str(e)}

def get_service_uptime(service_name: str, hours: int = 24) -> Dict[str, Any]:
    """Get service uptime statistics"""
    return health_checker.get_service_uptime(service_name, hours)

def get_health_summary() -> Dict[str, Any]:
    """Get comprehensive health summary"""
    return health_checker.get_health_summary()