from dataclasses import dataclass
from typing import Optional


@dataclass
class RedisConfig:
    cache_port: int = 13000
    queue_port: int = 11000
    version: Optional[str] = None

    @property
    def is_single_instance(self) -> bool:
        return self.cache_port == self.queue_port
