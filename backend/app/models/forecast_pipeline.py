"""Forecast pipeline persistence models."""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Date,
    Boolean,
    ForeignKey,
    Index,
    JSON,
    Text,
)
from sqlalchemy.orm import relationship

from .base import Base


class ForecastPipelineConfig(Base):
    __tablename__ = "forecast_pipeline_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    description = Column(Text)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False, index=True)

    time_bucket = Column(String(10), nullable=False, default="W")
    forecast_horizon = Column(Integer, nullable=False, default=8)
    min_clusters = Column(Integer, nullable=False, default=2)
    max_clusters = Column(Integer, nullable=False, default=8)
    min_observations = Column(Integer, nullable=False, default=12)
    forecast_metric = Column(String(20), nullable=False, default="wape")
    model_type = Column(String(50), nullable=False, default="clustered_naive")
    parameters = Column(JSON)

    # --- Dataset & Column Mapping (nullable = use system default) ---
    demand_item = Column(String(100), nullable=True)       # Product column override
    demand_point = Column(String(100), nullable=True)      # Site column override
    target_column = Column(String(100), nullable=True)     # Quantity column override
    date_column = Column(String(100), nullable=True)       # Date column override

    # --- Forecast Settings ---
    number_of_items_analyzed = Column(Integer, nullable=True)  # Max items (None = all)

    # --- Data Quality Thresholds ---
    ignore_numeric_columns = Column(Text, nullable=True)       # Comma-separated columns to exclude
    cv_sq_threshold = Column(Float, nullable=False, default=0.49)   # Demand variability cutoff
    adi_threshold = Column(Float, nullable=False, default=1.32)     # Demand intermittency cutoff

    # --- Clustering Configuration ---
    min_cluster_size = Column(Integer, nullable=False, default=5)
    min_cluster_size_uom = Column(String(20), nullable=False, default="items")  # items | percent
    cluster_selection_method = Column(String(50), nullable=False, default="KMeans")
    # Valid: KMeans, HDBSCAN, Agglomerative, OPTICS, Birch, GaussianMixture, MeanShift, Spectral, AffinityPropagation

    # --- Feature Engineering ---
    characteristics_creation_method = Column(String(30), nullable=False, default="tsfresh")  # tsfresh | classifier | both
    feature_correlation_threshold = Column(Float, nullable=False, default=0.8)
    feature_importance_method = Column(String(30), nullable=False, default="LassoCV")  # LassoCV | RandomForest | MutualInformation
    feature_importance_threshold = Column(Float, nullable=False, default=0.01)
    pca_variance_threshold = Column(Float, nullable=False, default=0.95)
    pca_importance_threshold = Column(Float, nullable=False, default=0.01)

    is_active = Column(Boolean, nullable=False, default=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    runs = relationship("ForecastPipelineRun", back_populates="pipeline_config", cascade="all, delete-orphan")


class ForecastPipelineRun(Base):
    __tablename__ = "forecast_pipeline_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_config_id = Column(Integer, ForeignKey("forecast_pipeline_config.id", ondelete="CASCADE"), nullable=False, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False, index=True)

    status = Column(String(30), nullable=False, default="pending")  # pending, running, completed, failed, published
    error_message = Column(Text)
    run_log = Column(JSON)

    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    model_type = Column(String(50), nullable=False, default="clustered_naive")
    forecast_metric = Column(String(20), nullable=False, default="wape")
    records_processed = Column(Integer)

    pipeline_config = relationship("ForecastPipelineConfig", back_populates="runs")
    predictions = relationship("ForecastPipelinePrediction", back_populates="run", cascade="all, delete-orphan")


class ForecastPipelineCluster(Base):
    __tablename__ = "forecast_pipeline_cluster"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("forecast_pipeline_run.id", ondelete="CASCADE"), nullable=False, index=True)
    unique_id = Column(String(200), nullable=False)
    product_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    cluster_id = Column(Integer, nullable=False)
    centroid_features = Column(JSON)

    __table_args__ = (
        Index("ix_fp_cluster_run_unique", "run_id", "unique_id"),
        Index("ix_fp_cluster_run_cluster", "run_id", "cluster_id"),
    )


class ForecastPipelinePrediction(Base):
    __tablename__ = "forecast_pipeline_prediction"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("forecast_pipeline_run.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    forecast_date = Column(Date, nullable=False, index=True)

    cluster_id = Column(Integer)
    model_name = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False, default="v1")

    forecast_p10 = Column(Float)
    forecast_p50 = Column(Float, nullable=False)
    forecast_median = Column(Float)
    forecast_p90 = Column(Float)

    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime)

    run = relationship("ForecastPipelineRun", back_populates="predictions")

    __table_args__ = (
        Index("ix_fp_pred_run_prod_site_date", "run_id", "product_id", "site_id", "forecast_date"),
    )


class ForecastPipelineMetric(Base):
    __tablename__ = "forecast_pipeline_metric"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("forecast_pipeline_run.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_scope = Column(String(20), nullable=False)  # overall, cluster
    scope_key = Column(String(100), nullable=False, default="overall")
    metric_name = Column(String(30), nullable=False)  # wape, mae, rmse
    metric_value = Column(Float, nullable=False)
    sample_size = Column(Integer)

    __table_args__ = (
        Index("ix_fp_metric_run_scope_name", "run_id", "metric_scope", "scope_key", "metric_name"),
    )


class ForecastPipelineFeatureImportance(Base):
    __tablename__ = "forecast_pipeline_feature_importance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("forecast_pipeline_run.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_name = Column(String(100), nullable=False)
    importance_score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_fp_importance_run_rank", "run_id", "rank"),
    )


class ForecastPipelinePublishLog(Base):
    __tablename__ = "forecast_pipeline_publish_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("forecast_pipeline_run.id", ondelete="CASCADE"), nullable=False, index=True)

    published_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    published_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    records_published = Column(Integer, nullable=False, default=0)
    notes = Column(Text)

    __table_args__ = (
        Index("ix_fp_publish_run", "run_id"),
    )
