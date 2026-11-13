from fastapi import APIRouter, status

HEALTH_PATH = "/health"

router = APIRouter(include_in_schema=False)


@router.get(HEALTH_PATH, status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    return {"status": "ok"}
