from common.http import HttpServerConfig
from common.settings import BaseServiceSettings
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:////data/router.db"

DEFAULT_NOTIFIER_BASE_URL = "http://notifier:8000"
DEFAULT_NOTIFIER_TIMEOUT_SECONDS = 10.0
DEFAULT_NOTIFIER_MAX_RETRIES = 3

DEFAULT_LLM_BASE_URL = "http://ollama:11434/v1"
DEFAULT_LLM_MODEL = "qwen2.5:3b"
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
DEFAULT_LLM_TEMPERATURE = 0.0

DEFAULT_WORKER_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_WORKER_MAX_ATTEMPTS = 5
DEFAULT_WORKER_HEARTBEAT_PATH = "/tmp/router-agent.alive"  # noqa: S108


class NotifierConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str = DEFAULT_NOTIFIER_BASE_URL
    timeout_seconds: float = Field(default=DEFAULT_NOTIFIER_TIMEOUT_SECONDS, gt=0)
    max_retries: int = Field(default=DEFAULT_NOTIFIER_MAX_RETRIES, ge=0)


class LlmConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str = DEFAULT_LLM_BASE_URL
    model: str = DEFAULT_LLM_MODEL
    timeout_seconds: float = Field(default=DEFAULT_LLM_TIMEOUT_SECONDS, gt=0)
    temperature: float = Field(default=DEFAULT_LLM_TEMPERATURE, ge=0)


class WorkerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    poll_interval_seconds: float = Field(default=DEFAULT_WORKER_POLL_INTERVAL_SECONDS, gt=0)
    max_attempts: int = Field(default=DEFAULT_WORKER_MAX_ATTEMPTS, ge=1)
    heartbeat_path: str = DEFAULT_WORKER_HEARTBEAT_PATH


class RouterSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
        env_prefix="ROUTER_",
        env_nested_delimiter="__",
    )

    http: HttpServerConfig = Field(default_factory=HttpServerConfig)
    database_url: str = DEFAULT_DATABASE_URL
    notifier: NotifierConfig = Field(default_factory=NotifierConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
