from pydantic import BaseModel, ConfigDict, Field

DEFAULT_HTTP_HOST = "0.0.0.0"  # noqa: S104 -- bind inside containers; compose networks gate access
DEFAULT_HTTP_PORT = 8000
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65_535


class HttpServerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = DEFAULT_HTTP_HOST
    port: int = Field(default=DEFAULT_HTTP_PORT, ge=MIN_TCP_PORT, le=MAX_TCP_PORT)
