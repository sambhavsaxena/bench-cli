from dataclasses import dataclass


@dataclass
class GunicornConfig:
    workers: int = 4
    threads: int = 4
    timeout: int = 120
    worker_class: str = "sync"
    malloc_arena_max: int = 2  # cap glibc malloc arenas; 0 = unset
    max_requests: int = 0  # recycle web worker after N requests to release heap; 0 = disabled
    max_requests_jitter: int = 0
