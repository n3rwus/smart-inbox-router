from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from notifier.ports.smtp_probe import SmtpProbe

HEALTH_PATH = "/health"
READY_PATH = "/ready"

router = APIRouter(include_in_schema=False)


def get_probe(request: Request) -> SmtpProbe:
    return cast(SmtpProbe, request.app.state.smtp_probe)


@router.get(HEALTH_PATH, status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(READY_PATH, status_code=status.HTTP_200_OK)
async def ready(probe: Annotated[SmtpProbe, Depends(get_probe)]) -> dict[str, str]:
    await probe.probe()
    return {"status": "ready"}
