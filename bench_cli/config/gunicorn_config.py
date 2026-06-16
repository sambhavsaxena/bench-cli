from dataclasses import dataclass


@dataclass
class GunicornConfig:
    workers: int = 4
    threads: int = 4
    timeout: int = 120
    worker_class: str = "sync"
