from dataclasses import dataclass


@dataclass
class GunicornConfig:
    workers: int = 4
    threads: int = 4
    timeout: int = 120
    worker_class: str = "sync"
    malloc_arena_max: int = 2  # MALLOC_ARENA_MAX for Python procs (pymalloc only); 0/absent = unset
    # Allocator for the Python procs. "pymalloc" (default) is stock CPython on
    # glibc — best throughput, for production. "jemalloc" LD_PRELOADs jemalloc
    # tuned to release freed memory to the OS immediately (MADV_DONTNEED) — for
    # small/demo benches and memory-overcommitted hosts. Falls back to pymalloc
    # if libjemalloc is not installed.
    memory_allocator: str = "pymalloc"
