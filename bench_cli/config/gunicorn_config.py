from dataclasses import dataclass


@dataclass
class GunicornConfig:
    workers: int = 4
    threads: int = 4
    timeout: int = 120
    worker_class: str = "sync"
    malloc_arena_max: int = 2  # MALLOC_ARENA_MAX for Python procs (pymalloc only); 0/absent = unset
    # Memory allocator for the Python procs: "auto" uses jemalloc when the lib is
    # present on the host, else pymalloc; "jemalloc"/"pymalloc" force the choice.
    memory_allocator: str = "auto"
