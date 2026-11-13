from fastapi import APIRouter, status

HEALTH_PATH = "/health"

router = APIRouter(tags=["health"])


@router.get(HEALTH_PATH, status_code=status.HTTP_204_NO_CONTENT)
async def health() -> None:
    return None
