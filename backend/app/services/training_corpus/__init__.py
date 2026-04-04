"""
Training Corpus Service — unified training data for all 4 planning layers.

See docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md

Public API:
  - TrainingCorpusService: main entry point
  - ERPBaselineSnapshot: dataclass for the anchor
  - PerturbationGenerator: generates N perturbations
  - SimulationRunner: runs Digital Twin with TRMs
  - TrainingCorpusAggregator: rolls up Level 1 -> 1.5, 2, 4
  - ThetaStarInferencer: derives policy params from TRM decisions
"""

from .corpus_service import TrainingCorpusService
from .erp_baseline_extractor import ERPBaselineExtractor, ERPBaselineSnapshot
from .perturbation_generator import PerturbationGenerator, PerturbationParams
from .simulation_runner import SimulationRunner
from .aggregator import TrainingCorpusAggregator
from .theta_inference import ThetaStarInferencer

__all__ = [
    "TrainingCorpusService",
    "ERPBaselineExtractor",
    "ERPBaselineSnapshot",
    "PerturbationGenerator",
    "PerturbationParams",
    "SimulationRunner",
    "TrainingCorpusAggregator",
    "ThetaStarInferencer",
]
