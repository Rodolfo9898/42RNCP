"""Is an X server answering? Standard library only (the sandbox image has no dependencies)."""

import socket
from pathlib import Path


class DisplayProbe:
    """Connects to the X server's socket of one display number, the way a client would."""

    def __init__(self, number: str, directory: Path) -> None:
        self.number, self.directory = number, directory

    def is_up(self) -> bool:
        for address in (f"\0{self.directory}/X{self.number}", str(self.directory / f"X{self.number}")):      # (Linux: the abstract socket, then the file)
            probe = socket.socket(socket.AF_UNIX)
            probe.settimeout(0.2)
            try:
                probe.connect(address)
                return True
            except OSError:
                pass
            finally:
                probe.close()
        return False
