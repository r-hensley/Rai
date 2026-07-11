from dataclasses import dataclass


@dataclass(frozen=True)
class ActivitySnapshot:
    bucket_labels: tuple[str, ...]
    bucket_counts: tuple[int, ...]
    total_messages: int
    active_users: int
    active_channels: int
    coverage_minutes: int
    top_channels: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class HealthCheck:
    label: str
    detail: str
    level: str


@dataclass(frozen=True)
class TaskSnapshot:
    name: str
    state: str
    level: str
    next_run: str
    iterations: int


@dataclass(frozen=True)
class Metric:
    label: str
    value: str
    detail: str
    level: str = "neutral"
