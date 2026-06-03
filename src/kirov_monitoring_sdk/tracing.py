import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_current_context: ContextVar[Optional["TraceContext"]] = ContextVar("trace_context", default=None)


@dataclass
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    _start: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass
class Span:
    name: str
    context: TraceContext
    _end: float = 0.0

    def finish(self) -> None:
        self._end = datetime.now(timezone.utc).timestamp()

    @property
    def duration_ms(self) -> float:
        end = self._end or datetime.now(timezone.utc).timestamp()
        return round((end - self.context._start) * 1000, 2)


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def start_span(name: str, context: Optional[TraceContext] = None) -> Span:
    parent = context or _current_context.get()
    span_id = _new_id()
    ctx = TraceContext(
        trace_id=parent.trace_id if parent else _new_id(),
        span_id=span_id,
        parent_span_id=parent.span_id if parent else None,
    )
    _current_context.set(ctx)
    return Span(name=name, context=ctx)


def trace_to_headers(context: TraceContext) -> dict[str, str]:
    return {
        "X-Trace-Id": context.trace_id,
        "X-Span-Id": context.span_id,
        "X-Parent-Span-Id": context.parent_span_id or "",
    }


def headers_to_trace(headers: dict[str, str]) -> Optional[TraceContext]:
    trace_id = headers.get("X-Trace-Id") or headers.get("x-trace-id")
    span_id = headers.get("X-Span-Id") or headers.get("x-span-id")
    if not trace_id or not span_id:
        return None
    parent_span_id = headers.get("X-Parent-Span-Id") or headers.get("x-parent-span-id")
    return TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id or None,
    )
