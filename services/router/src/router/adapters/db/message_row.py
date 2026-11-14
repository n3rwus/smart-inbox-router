from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from router.adapters.db.base import Base

SENDER_EMAIL_MAX_LEN = 320
STATUS_MAX_LEN = 16
DEPARTMENT_MAX_LEN = 32
ERROR_CODE_MAX_LEN = 64
MESSAGE_ID_LEN = 36


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(MESSAGE_ID_LEN), primary_key=True)
    sender_email: Mapped[str] = mapped_column(String(SENDER_EMAIL_MAX_LEN))
    body: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(String(STATUS_MAX_LEN))
    department: Mapped[str | None] = mapped_column(String(DEPARTMENT_MAX_LEN), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(ERROR_CODE_MAX_LEN), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()
    available_at: Mapped[datetime] = mapped_column()

    __table_args__ = (Index("ix_messages_status_available_at", "status", "available_at"),)
