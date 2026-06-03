import threading
from collections import defaultdict
from typing import Optional


class _Metric:
    def __init__(self, name: str, help_text: str = ""):
        self.name = name
        self.help_text = help_text


class Counter(_Metric):
    def __init__(self, name: str, help_text: str = ""):
        super().__init__(name, help_text)
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, labels: Optional[dict] = None, value: float = 1.0):
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key] += value

    def collect(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        for labels, val in self._values.items():
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f'{self.name}{{{label_str}}} {val}')
        return lines


class Gauge(_Metric):
    def __init__(self, name: str, help_text: str = ""):
        super().__init__(name, help_text)
        self._values: dict[tuple, float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, labels: Optional[dict] = None):
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key] = value

    def collect(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        for labels, val in self._values.items():
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f'{self.name}{{{label_str}}} {val}')
        return lines


class Histogram(_Metric):
    def __init__(self, name: str, help_text: str = "", buckets: Optional[list[float]] = None):
        super().__init__(name, help_text)
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._values: dict[tuple, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[dict] = None):
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key].append(value)

    def collect(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        for labels, vals in self._values.items():
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            count = len(vals)
            total = sum(vals)
            bucket_counts = defaultdict(int)
            for v in vals:
                for b in self.buckets:
                    if v <= b:
                        bucket_counts[b] += 1
            for b in self.buckets:
                lines.append(f'{self.name}_bucket{{{label_str},le="{b}"}} {bucket_counts[b]}')
            lines.append(f'{self.name}_bucket{{{label_str},le="+Inf"}} {count}')
            lines.append(f'{self.name}_count{{{label_str}}} {count}')
            lines.append(f'{self.name}_sum{{{label_str}}} {total}')
        return lines


class MetricsCollector:
    def __init__(self):
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, labels: Optional[dict] = None, value: float = 1.0):
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name)
            self._counters[name].inc(labels, value)

    def gauge(self, name: str, value: float, labels: Optional[dict] = None):
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name)
            self._gauges[name].set(value, labels)

    def observe(self, name: str, value: float, labels: Optional[dict] = None):
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name)
            self._histograms[name].observe(value, labels)

    def export_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for c in self._counters.values():
                lines.extend(c.collect())
            for g in self._gauges.values():
                lines.extend(g.collect())
            for h in self._histograms.values():
                lines.extend(h.collect())
        return "\n".join(lines)
