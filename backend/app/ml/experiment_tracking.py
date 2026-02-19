"""
MLflow Experiment Tracking Integration

Provides comprehensive experiment tracking and model management:
- Automatic experiment logging (parameters, metrics, artifacts)
- Model versioning and registry
- Run comparison and visualization
- Artifact storage (models, plots, datasets)
- Integration with training pipelines
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)

# Optional MLflow dependency
try:
    import mlflow
    import mlflow.pytorch
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None
    MlflowClient = None

# Forward reference for type hints when MLflow is not available
if not MLFLOW_AVAILABLE:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from mlflow import ActiveRun  # noqa: F401
    else:
        ActiveRun = None  # noqa: F811


class ExperimentTracker:
    """
    MLflow-based experiment tracking for model training.

    Features:
    - Automatic parameter logging
    - Real-time metric tracking
    - Model artifact storage
    - Run comparison
    - Model registry integration
    """

    def __init__(
        self,
        tracking_uri: str = "file:./mlruns",
        experiment_name: str = "Autonomy ML",
        registry_uri: Optional[str] = None
    ):
        """
        Initialize experiment tracker.

        Args:
            tracking_uri: MLflow tracking server URI
            experiment_name: Name of the experiment
            registry_uri: Model registry URI (defaults to tracking_uri)
        """
        if not MLFLOW_AVAILABLE:
            raise RuntimeError("MLflow is not available. Install with: pip install mlflow")

        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        self.registry_uri = registry_uri or tracking_uri

        # Set tracking URI
        mlflow.set_tracking_uri(tracking_uri)

        # Set or create experiment
        self.experiment = mlflow.set_experiment(experiment_name)
        self.experiment_id = self.experiment.experiment_id

        # Initialize client
        self.client = MlflowClient(tracking_uri=tracking_uri)

        logger.info(f"MLflow tracker initialized: experiment='{experiment_name}', uri='{tracking_uri}'")

    def start_run(
        self,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        nested: bool = False
    ) -> "mlflow.ActiveRun":
        """
        Start a new MLflow run.

        Args:
            run_name: Name for the run
            tags: Tags to attach to the run
            nested: Whether this is a nested run

        Returns:
            active_run: MLflow active run context
        """
        tags = tags or {}

        # Add default tags
        tags.update({
            "project": "Autonomy",
            "framework": "PyTorch",
            "started_at": datetime.utcnow().isoformat()
        })

        run = mlflow.start_run(
            run_name=run_name,
            experiment_id=self.experiment_id,
            tags=tags,
            nested=nested
        )

        logger.info(f"Started MLflow run: {run.info.run_id} (name: {run_name})")

        return run

    def log_params(self, params: Dict[str, Any]):
        """
        Log parameters for the current run.

        Args:
            params: Dictionary of parameters
        """
        # Filter out non-serializable values
        serializable_params = {}
        for key, value in params.items():
            if isinstance(value, (int, float, str, bool)):
                serializable_params[key] = value
            else:
                serializable_params[key] = str(value)

        mlflow.log_params(serializable_params)
        logger.debug(f"Logged {len(serializable_params)} parameters")

    def log_param(self, key: str, value: Any):
        """Log a single parameter."""
        if not isinstance(value, (int, float, str, bool)):
            value = str(value)
        mlflow.log_param(key, value)

    def log_metrics(self, metrics: Dict[str, float], step: Optional[int] = None):
        """
        Log metrics for the current run.

        Args:
            metrics: Dictionary of metric name -> value
            step: Optional step number (e.g., epoch)
        """
        mlflow.log_metrics(metrics, step=step)
        logger.debug(f"Logged {len(metrics)} metrics at step {step}")

    def log_metric(self, key: str, value: float, step: Optional[int] = None):
        """Log a single metric."""
        mlflow.log_metric(key, value, step=step)

    def log_model(
        self,
        model: Any,
        artifact_path: str,
        registered_model_name: Optional[str] = None,
        **kwargs
    ):
        """
        Log a PyTorch model.

        Args:
            model: PyTorch model to log
            artifact_path: Path within run artifacts
            registered_model_name: Name for model registry
            **kwargs: Additional arguments for mlflow.pytorch.log_model
        """
        try:
            import torch.nn as nn

            if not isinstance(model, nn.Module):
                logger.warning(f"Model is not a PyTorch Module, using pickle")
                mlflow.log_dict({"model_type": str(type(model))}, "model_info.json")
                return

            mlflow.pytorch.log_model(
                pytorch_model=model,
                artifact_path=artifact_path,
                registered_model_name=registered_model_name,
                **kwargs
            )

            logger.info(f"Logged model to '{artifact_path}'")

            if registered_model_name:
                logger.info(f"Registered model: {registered_model_name}")

        except Exception as e:
            logger.error(f"Failed to log model: {str(e)}")
            # Fallback: log model state dict
            if hasattr(model, 'state_dict'):
                import torch
                temp_path = Path(f"/tmp/model_{datetime.utcnow().timestamp()}.pth")
                torch.save(model.state_dict(), temp_path)
                mlflow.log_artifact(str(temp_path), artifact_path)
                temp_path.unlink()

    def log_artifact(self, local_path: str, artifact_path: Optional[str] = None):
        """
        Log an artifact file.

        Args:
            local_path: Path to local file
            artifact_path: Destination path in artifacts
        """
        mlflow.log_artifact(local_path, artifact_path)
        logger.debug(f"Logged artifact: {local_path}")

    def log_artifacts(self, local_dir: str, artifact_path: Optional[str] = None):
        """
        Log all files in a directory.

        Args:
            local_dir: Local directory path
            artifact_path: Destination path in artifacts
        """
        mlflow.log_artifacts(local_dir, artifact_path)
        logger.debug(f"Logged artifacts from: {local_dir}")

    def log_dict(self, dictionary: Dict[str, Any], artifact_file: str):
        """
        Log a dictionary as JSON artifact.

        Args:
            dictionary: Dictionary to log
            artifact_file: Filename for the artifact
        """
        mlflow.log_dict(dictionary, artifact_file)
        logger.debug(f"Logged dictionary to: {artifact_file}")

    def log_figure(self, figure, artifact_file: str):
        """
        Log a matplotlib figure.

        Args:
            figure: Matplotlib figure
            artifact_file: Filename for the artifact
        """
        try:
            mlflow.log_figure(figure, artifact_file)
            logger.debug(f"Logged figure: {artifact_file}")
        except Exception as e:
            logger.error(f"Failed to log figure: {str(e)}")

    def log_text(self, text: str, artifact_file: str):
        """
        Log text content.

        Args:
            text: Text content
            artifact_file: Filename for the artifact
        """
        mlflow.log_text(text, artifact_file)
        logger.debug(f"Logged text to: {artifact_file}")

    def end_run(self, status: str = "FINISHED"):
        """
        End the current run.

        Args:
            status: Run status (FINISHED, FAILED, KILLED)
        """
        mlflow.end_run(status=status)
        logger.info(f"Ended MLflow run with status: {status}")

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """
        Get run information.

        Args:
            run_id: MLflow run ID

        Returns:
            run_data: Run information
        """
        run = self.client.get_run(run_id)

        return {
            "run_id": run.info.run_id,
            "experiment_id": run.info.experiment_id,
            "status": run.info.status,
            "start_time": run.info.start_time,
            "end_time": run.info.end_time,
            "artifact_uri": run.info.artifact_uri,
            "params": run.data.params,
            "metrics": run.data.metrics,
            "tags": run.data.tags
        }

    def search_runs(
        self,
        filter_string: Optional[str] = None,
        order_by: Optional[List[str]] = None,
        max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Search runs in the experiment.

        Args:
            filter_string: Filter expression (e.g., "params.architecture = 'enhanced'")
            order_by: Sort order (e.g., ["metrics.loss ASC"])
            max_results: Maximum number of results

        Returns:
            runs: List of run information
        """
        runs = mlflow.search_runs(
            experiment_ids=[self.experiment_id],
            filter_string=filter_string,
            order_by=order_by,
            max_results=max_results
        )

        return runs.to_dict('records') if not runs.empty else []

    def get_best_run(
        self,
        metric_name: str,
        ascending: bool = True,
        filter_string: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the best run by a metric.

        Args:
            metric_name: Metric to optimize
            ascending: True for minimization, False for maximization
            filter_string: Optional filter

        Returns:
            best_run: Best run information or None
        """
        order = "ASC" if ascending else "DESC"
        runs = self.search_runs(
            filter_string=filter_string,
            order_by=[f"metrics.{metric_name} {order}"],
            max_results=1
        )

        return runs[0] if runs else None

    def compare_runs(
        self,
        run_ids: List[str],
        metric_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare multiple runs.

        Args:
            run_ids: List of run IDs to compare
            metric_names: Metrics to compare (None = all metrics)

        Returns:
            comparison: Comparison data
        """
        runs_data = [self.get_run(run_id) for run_id in run_ids]

        comparison = {
            "runs": runs_data,
            "metrics_comparison": {},
            "params_comparison": {}
        }

        # Compare metrics
        all_metrics = set()
        for run in runs_data:
            all_metrics.update(run["metrics"].keys())

        for metric in all_metrics:
            if metric_names is None or metric in metric_names:
                comparison["metrics_comparison"][metric] = {
                    run["run_id"]: run["metrics"].get(metric)
                    for run in runs_data
                }

        # Compare parameters
        all_params = set()
        for run in runs_data:
            all_params.update(run["params"].keys())

        for param in all_params:
            comparison["params_comparison"][param] = {
                run["run_id"]: run["params"].get(param)
                for run in runs_data
            }

        return comparison

    def register_model(
        self,
        model_uri: str,
        name: str,
        tags: Optional[Dict[str, str]] = None,
        description: Optional[str] = None
    ) -> str:
        """
        Register a model in the model registry.

        Args:
            model_uri: URI of the model (e.g., "runs:/<run_id>/model")
            name: Model name in registry
            tags: Tags for the model version
            description: Model description

        Returns:
            version: Model version number
        """
        result = mlflow.register_model(model_uri, name)

        # Add tags and description if provided
        if tags:
            for key, value in tags.items():
                self.client.set_model_version_tag(name, result.version, key, value)

        if description:
            self.client.update_model_version(
                name=name,
                version=result.version,
                description=description
            )

        logger.info(f"Registered model '{name}' version {result.version}")

        return result.version

    def transition_model_stage(
        self,
        name: str,
        version: str,
        stage: str,
        archive_existing_versions: bool = False
    ):
        """
        Transition model to a different stage.

        Args:
            name: Model name
            version: Model version
            stage: Target stage (Staging, Production, Archived, None)
            archive_existing_versions: Archive existing versions in target stage
        """
        self.client.transition_model_version_stage(
            name=name,
            version=version,
            stage=stage,
            archive_existing_versions=archive_existing_versions
        )

        logger.info(f"Transitioned model '{name}' v{version} to {stage}")

    def get_latest_model_version(
        self,
        name: str,
        stage: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest model version.

        Args:
            name: Model name
            stage: Optional stage filter (Production, Staging, etc.)

        Returns:
            model_version: Model version information
        """
        try:
            if stage:
                versions = self.client.get_latest_versions(name, stages=[stage])
            else:
                versions = self.client.search_model_versions(f"name='{name}'")

            if not versions:
                return None

            latest = versions[0]

            return {
                "name": latest.name,
                "version": latest.version,
                "stage": latest.current_stage,
                "description": latest.description,
                "run_id": latest.run_id,
                "source": latest.source,
                "tags": latest.tags
            }

        except Exception as e:
            logger.error(f"Failed to get model version: {str(e)}")
            return None

    def log_training_run(
        self,
        run_name: str,
        params: Dict[str, Any],
        metrics_history: Dict[str, List[float]],
        model: Any,
        artifacts: Optional[Dict[str, str]] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Log a complete training run.

        Convenience method that logs everything in one call.

        Args:
            run_name: Name for the run
            params: Training parameters
            metrics_history: Metrics over time (e.g., {"loss": [0.5, 0.4, 0.3]})
            model: Trained model
            artifacts: Additional artifacts {artifact_name: local_path}
            tags: Run tags

        Returns:
            run_id: MLflow run ID
        """
        with self.start_run(run_name=run_name, tags=tags):
            # Log parameters
            self.log_params(params)

            # Log metrics history
            for metric_name, values in metrics_history.items():
                for step, value in enumerate(values):
                    self.log_metric(metric_name, value, step=step)

            # Log final metrics
            final_metrics = {
                f"final_{name}": values[-1]
                for name, values in metrics_history.items()
                if values
            }
            self.log_metrics(final_metrics)

            # Log model
            self.log_model(model, artifact_path="model")

            # Log additional artifacts
            if artifacts:
                for artifact_name, local_path in artifacts.items():
                    self.log_artifact(local_path, artifact_path=artifact_name)

            run_id = mlflow.active_run().info.run_id

        logger.info(f"Logged complete training run: {run_id}")

        return run_id


def get_or_create_tracker(
    tracking_uri: Optional[str] = None,
    experiment_name: str = "Autonomy ML"
) -> ExperimentTracker:
    """
    Get or create an experiment tracker.

    Args:
        tracking_uri: MLflow tracking server URI
        experiment_name: Experiment name

    Returns:
        tracker: ExperimentTracker instance
    """
    if tracking_uri is None:
        # Use default local tracking
        tracking_uri = "file:./mlruns"

    return ExperimentTracker(
        tracking_uri=tracking_uri,
        experiment_name=experiment_name
    )
