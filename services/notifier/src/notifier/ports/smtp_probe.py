from typing import Protocol


class SmtpProbe(Protocol):
    async def probe(self) -> None:
        """Verify SMTP reachability. Raise NotReadyError on failure."""
