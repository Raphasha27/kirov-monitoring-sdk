import asyncio
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

from fastapi import APIRouter


@dataclass
class HealthCheck:
    name: str
    check_fn: Callable[[], Coroutine[Any, Any, dict]]
    timeout: float = 5.0


@dataclass
class HealthEntry:
    name: str
    status: str
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class HealthRegistry:
    checks: list[HealthCheck] = field(default_factory=list)

    def register(self, check: HealthCheck) -> None:
        self.checks.append(check)

    def unregister(self, name: str) -> None:
        self.checks = [c for c in self.checks if c.name != name]


async def _db_check() -> dict:
    return {"status": "pass", "detail": "No database configured"}


async def _redis_check() -> dict:
    return {"status": "pass", "detail": "No Redis configured"}


async def _disk_check() -> dict:
    usage = shutil.disk_usage("/")
    free_gb = usage.free / (1024**3)
    status = "pass" if free_gb > 1.0 else "warn"
    return {"status": status, "detail": f"{free_gb:.1f}GB free"}


async def _memory_check() -> dict:
    try:
        import psutil
        mem = psutil.virtual_memory()
        free_mb = mem.available / (1024**2)
        status = "pass" if mem.available > 500 * 1024 * 1024 else "warn"
        return {"status": status, "detail": f"{free_mb:.0f}MB available"}
    except ImportError:
        return {"status": "pass", "detail": "psutil not installed, memory check skipped"}


def DatabaseHealthCheck() -> HealthCheck:
    return HealthCheck(name="database", check_fn=_db_check)


def RedisHealthCheck() -> HealthCheck:
    return HealthCheck(name="redis", check_fn=_redis_check)


def DiskSpaceHealthCheck() -> HealthCheck:
    return HealthCheck(name="disk_space", check_fn=_disk_check)


def MemoryHealthCheck() -> HealthCheck:
    return HealthCheck(name="memory", check_fn=_memory_check)


class HealthRouter:
    def __init__(self, registry: Optional[HealthRegistry] = None):
        self._registry = registry or HealthRegistry()
        self._router = APIRouter()
        self._router.add_api_route("/health", self._handle_liveness, methods=["GET"])
        self._router.add_api_route("/health/ready", self._handle_readiness, methods=["GET"])

    @property
    def router(self) -> APIRouter:
        return self._router

    async def _run_checks(self) -> list[HealthEntry]:
        results: list[HealthEntry] = []
        for check in self._registry.checks:
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(check.check_fn(), timeout=check.timeout)
                elapsed = (time.monotonic() - start) * 1000
                results.append(
                    HealthEntry(
                        name=check.name,
                        status=result.get("status", "pass"),
                        detail=result.get("detail", ""),
                        duration_ms=round(elapsed, 2),
                    )
                )
            except asyncio.TimeoutError:
                elapsed = (time.monotonic() - start) * 1000
                results.append(
                    HealthEntry(
                        name=check.name,
                        status="warn",
                        detail="timeout",
                        duration_ms=round(elapsed, 2),
                    )
                )
            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                results.append(
                    HealthEntry(
                        name=check.name,
                        status="fail",
                        detail=str(e),
                        duration_ms=round(elapsed, 2),
                    )
                )
        return results

    def _build_response(self, results: list[HealthEntry], overall: str) -> dict:
        return {
            "status": overall,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": [
                {
                    "name": r.name,
                    "status": r.status,
                    "detail": r.detail,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
        }

    async def _handle_liveness(self) -> dict:
        return {
            "status": "pass",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _handle_readiness(self) -> dict:
        results = await self._run_checks()
        overall = "pass"
        for r in results:
            if r.status == "fail":
                overall = "fail"
            elif r.status == "warn" and overall != "fail":
                overall = "warn"
        return self._build_response(results, overall)
