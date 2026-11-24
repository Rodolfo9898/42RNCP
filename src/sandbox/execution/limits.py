"""What a command may consume: the ceilings it runs under."""

import resource


class ResourceLimits:
    """The ceilings applied to a command between fork and exec (`apply` is the `preexec_fn`).

    No RLIMIT_NPROC: the kernel counts it per uid across the whole host, and uid 1000 is usually the Linux host's own user (with a
    browser's worth of threads), so every fork would fail. pids_limit in docker-compose.yml caps the number of processes of this
    container alone."""

    def __init__(self, cpu_seconds: int, file_bytes: int = 200 * 1024 * 1024) -> None:
        self.cpu_seconds, self.file_bytes = cpu_seconds, file_bytes

    def apply(self) -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (self.file_bytes,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_seconds, self.cpu_seconds))
