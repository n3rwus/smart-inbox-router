from typing import cast

from fastapi import APIRouter, Request, status

from notifier.ports.smtp_probe import SmtpProbe

HEALTH_PATH = "/health"
READY_PATH = "/ready"

router = APIRouter(include_in_schema=False)


@router.get(HEALTH_PATH, status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(READY_PATH, status_code=status.HTTP_200_OK)
async def ready(request: Request) -> dict[str, str]:
    probe = cast(SmtpProbe, request.app.state.smtp_probe)
    await probe.probe()
    return {"status": "ready"}
