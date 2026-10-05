from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    evaluation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # XGBoost_Failure_72h, Logistic_Baseline, IsolationForest, RUL_Regressor
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    metric_precision: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metric_recall: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metric_f1: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metric_roc_auc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metric_rul_rmse: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metric_rul_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # NASA asymmetric scoring function
    false_positive_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    false_negative_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
