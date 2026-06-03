import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

import structlog
from pydantic import BaseModel


class SecurityEvent(BaseModel):
    event_type: str
    user_id: Optional[str] = None
    resource: str = ""
    action: str = ""
    result: str = ""
    ip_address: Optional[str] = None
    timestamp: datetime = datetime.now(timezone.utc)
    metadata: dict = {}


def setup_logging(
    service_name: str,
    level: str = "INFO",
    json_output: bool = True,
) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]

    if json_output:
        shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    structlog.get_logger().info("Logging configured", service=service_name)


def log_security_event(event: SecurityEvent) -> None:
    logger = structlog.get_logger()
    logger.info(
        "security_event",
        event_type=event.event_type,
        user_id=event.user_id,
        resource=event.resource,
        action=event.action,
        result=event.result,
        ip_address=event.ip_address,
        timestamp=event.timestamp.isoformat(),
        metadata=json.dumps(event.metadata, default=str),
    )


class AuditLogger:
    def __init__(
        self,
        db_callback: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
    ):
        self._callback = db_callback

    async def log(self, event: SecurityEvent) -> None:
        log_security_event(event)
        if self._callback:
            await self._callback(event.model_dump())
