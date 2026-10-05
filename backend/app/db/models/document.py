from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentRecord(Base):
    __tablename__ = "document_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), default="PDF", nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    ocr_raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extracted_entities: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    aircraft_id: Mapped[Optional[str]] = mapped_column(ForeignKey("aircraft.id", ondelete="SET NULL"), nullable=True, index=True)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PROCESSED", nullable=False)  # PENDING, PROCESSED, FAILED
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
