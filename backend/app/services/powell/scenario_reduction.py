"""
Scenario Reduction for Stochastic Programming

Reduces large scenario sets to tractable sizes while preserving
solution quality. Uses Wasserstein distance for scenario selection.

Theory:
- Too many scenarios → computationally intractable
- Too few scenarios → lose coverage guarantees
- Scenario reduction → optimal trade-off

Key Insight:
- We want to find a small set of scenarios that approximates the original distribution
- Wasserstein distance measures how far apart two probability distributions are
- Forward selection greedily builds a representative set

References:
- Heitsch & Römisch (2003). Scenario Reduction Algorithms
- Dupačová, Gröwe-Kuska, Römisch (2003). Scenario Reduction
- Pflug (2001). Scenario tree generation
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging
import time

import numpy as np
from scipy.spatial.distance import cdist

from .stochastic_program import Scenario

logger = logging.getLogger(__name__)


@dataclass
class ScenarioReductionResult:
    """Result of scenario reduction"""

    reduced_scenarios: List[Scenario]
    original_count: int
    reduced_count: int
    wasserstein_error: float
    computation_time: float

    # Mapping: reduced scenario index -> list of original indices it represents
    scenario_mapping: Dict[int, List[int]]

    # Probability adjustments
    original_probabilities: List[float] = field(default_factory=list)
    aggregated_probabilities: List[float] = field(default_factory=list)

    def get_reduction_ratio(self) -> float:
        """Get the reduction ratio"""
        if self.original_count == 0:
            return 0.0
        return 1.0 - (self.reduced_count / self.original_count)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "original_count": self.original_count,
            "reduced_count": self.reduced_count,
            "reduction_ratio": self.get_reduction_ratio(),
            "wasserstein_error": self.wasserstein_error,
            "computation_time": self.computation_time,
            "scenario_mapping": self.scenario_mapping,
        }


class WassersteinScenarioReducer:
    """
    Reduces scenarios using Wasserstein distance-based forward selection.

    Algorithm (Forward Selection):
    1. Start with empty reduced set
    2. Iteratively add scenario that minimizes Wasserstein distance
    3. Stop when target size reached or error threshold met

    Preserves conformal coverage guarantees better than random sampling
    because it maintains the shape of the uncertainty region.

    Usage:
        reducer = WassersteinScenarioReducer()
        result = reducer.reduce(scenarios, target_count=30)
        reduced_scenarios = result.reduced_scenarios
    """

    def __init__(
        self,
        distance_metric: str = "euclidean",
        weights: Optional[Dict[str, float]] = None,
        normalize_features: bool = True,
    ):
        """
        Initialize reducer.

        Args:
            distance_metric: Distance metric ("euclidean", "manhattan", "chebyshev")
            weights: Feature weights for distance calculation
            normalize_features: Whether to normalize features before distance calculation
        """
        self.distance_metric = distance_metric
        self.weights = weights or {}
        self.normalize_features = normalize_features

    def reduce(
        self,
        scenarios: List[Scenario],
        target_count: int,
        method: str = "fast_forward",
    ) -> ScenarioReductionResult:
        """
        Reduce scenario set to target size.

        Args:
            scenarios: Original scenario list
            target_count: Target number of scenarios
            method: Reduction method
                - "forward_selection": Full forward selection (accurate but slow)
                - "backward_reduction": Backward reduction (more accurate, slower)
                - "fast_forward": K-medoids initialization (fast, good approximation)

        Returns:
            ScenarioReductionResult with reduced scenarios
        """
        start_time = time.time()

        if len(scenarios) <= target_count:
            logger.info(
                f"Scenario count ({len(scenarios)}) <= target ({target_count}), "
                "returning original"
            )
            return ScenarioReductionResult(
                reduced_scenarios=scenarios,
                original_count=len(scenarios),
                reduced_count=len(scenarios),
                wasserstein_error=0.0,
                computation_time=0.0,
                scenario_mapping={i: [i] for i in range(len(scenarios))},
                original_probabilities=[s.probability for s in scenarios],
                aggregated_probabilities=[s.probability for s in scenarios],
            )

        # Convert scenarios to feature matrix
        features = self._scenarios_to_features(scenarios)
        probabilities = np.array([s.probability for s in scenarios])

        if method == "forward_selection":
            selected, mapping = self._forward_selection(features, probabilities, target_count)
        elif method == "backward_reduction":
            selected, mapping = self._backward_reduction(features, probabilities, target_count)
        elif method == "fast_forward":
            selected, mapping = self._fast_forward_selection(features, probabilities, target_count)
        else:
            raise ValueError(f"Unknown method: {method}")

        # Create reduced scenario list with updated probabilities
        reduced_scenarios = []
        aggregated_probs = []

        for i, idx in enumerate(selected):
            scenario = scenarios[idx]
            # Aggregate probability from all scenarios mapped to this one
            aggregated_prob = sum(probabilities[j] for j in mapping[i])
            aggregated_probs.append(aggregated_prob)

            reduced_scenarios.append(
                Scenario(
                    id=i,
                    probability=aggregated_prob,
                    demand=scenario.demand.copy(),
                    lead_times=scenario.lead_times.copy(),
                    yields=scenario.yields.copy(),
                    capacities=scenario.capacities.copy() if scenario.capacities else {},
                )
            )

        # Compute Wasserstein error
        error = self._compute_wasserstein_error(
            features,
            probabilities,
            features[selected],
            np.array(aggregated_probs),
        )

        computation_time = time.time() - start_time

        logger.info(
            f"Reduced {len(scenarios)} scenarios to {len(reduced_scenarios)} "
            f"({method}): error={error:.4f}, time={computation_time:.2f}s"
        )

        return ScenarioReductionResult(
            reduced_scenarios=reduced_scenarios,
            original_count=len(scenarios),
            reduced_count=len(reduced_scenarios),
            wasserstein_error=error,
            computation_time=computation_time,
            scenario_mapping={i: mapping[i] for i in range(len(selected))},
            original_probabilities=[s.probability for s in scenarios],
            aggregated_probabilities=aggregated_probs,
        )

    def _scenarios_to_features(self, scenarios: List[Scenario]) -> np.ndarray:
        """
        Convert scenarios to feature matrix for distance calculations.

        Features include:
        - Total demand by product
        - Mean demand by product
        - Demand standard deviation by product
        - Lead times
        - Yields
        """
        features = []

        for scenario in scenarios:
            f = []

            # Demand features
            for prod in sorted(scenario.demand.keys()):
                demands = scenario.demand[prod]
                f.append(sum(demands))  # Total demand
                f.append(np.mean(demands))  # Mean demand
                f.append(np.std(demands) if len(demands) > 1 else 0)  # Demand variability

            # Lead time features
            for supplier in sorted(scenario.lead_times.keys()):
                lt = scenario.lead_times[supplier]
                f.append(lt)

            # Yield features
            for prod in sorted(scenario.yields.keys()):
                y = scenario.yields[prod]
                f.append(y)

            features.append(f)

        features = np.array(features)

        # Normalize features
        if self.normalize_features and features.shape[0] > 1:
            mean = features.mean(axis=0)
            std = features.std(axis=0)
            std[std == 0] = 1  # Avoid division by zero
            features = (features - mean) / std

        return features

    def _forward_selection(
        self,
        features: np.ndarray,
        probabilities: np.ndarray,
        target_count: int,
    ) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Forward selection: iteratively add best scenario.

        At each step, add the scenario that most reduces Wasserstein distance
        to the original distribution.

        O(n² * target_count) complexity
        """
        n = len(features)
        remaining = set(range(n))
        selected: List[int] = []

        # Precompute distance matrix
        distances = cdist(features, features, metric=self.distance_metric)

        while len(selected) < target_count and remaining:
            best_idx = None
            best_error = float("inf")

            for candidate in remaining:
                # Tentatively add candidate
                trial_selected = selected + [candidate]

                # Compute error with this selection
                error = self._compute_selection_error(
                    distances, probabilities, trial_selected, remaining - {candidate}
                )

                if error < best_error:
                    best_error = error
                    best_idx = candidate

            if best_idx is not None:
                selected.append(best_idx)
                remaining.remove(best_idx)

        # Assign remaining scenarios to nearest selected
        mapping = {i: [selected[i]] for i in range(len(selected))}

        for j in range(n):
            if j in selected:
                continue

            # Find nearest selected scenario
            nearest = min(range(len(selected)), key=lambda i: distances[j, selected[i]])
            mapping[nearest].append(j)

        return selected, mapping

    def _fast_forward_selection(
        self,
        features: np.ndarray,
        probabilities: np.ndarray,
        target_count: int,
    ) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Fast forward selection using k-medoids initialization.

        Much faster than full forward selection for large scenario sets.
        Uses k-means clustering to find representative scenarios.

        O(n * k * iterations) complexity
        """
        try:
            from sklearn.cluster import KMeans
        except ImportError:
            logger.warning("sklearn not available, falling back to forward selection")
            return self._forward_selection(features, probabilities, target_count)

        # Use k-means to find initial clusters
        kmeans = KMeans(n_clusters=target_count, random_state=42, n_init=10)
        labels = kmeans.fit_predict(features)

        # For each cluster, select scenario closest to centroid
        # weighted by probability
        selected = []
        mapping: Dict[int, List[int]] = {}

        for k in range(target_count):
            cluster_indices = np.where(labels == k)[0]

            if len(cluster_indices) == 0:
                continue

            # Select highest-probability scenario closest to centroid
            centroid = kmeans.cluster_centers_[k]
            distances_to_centroid = np.linalg.norm(features[cluster_indices] - centroid, axis=1)

            # Weight by probability (prefer high-probability scenarios near centroid)
            cluster_probs = probabilities[cluster_indices]
            scores = cluster_probs / (distances_to_centroid + 1e-10)

            best_in_cluster = cluster_indices[np.argmax(scores)]

            selected.append(best_in_cluster)
            mapping[len(selected) - 1] = list(cluster_indices)

        return selected, mapping

    def _backward_reduction(
        self,
        features: np.ndarray,
        probabilities: np.ndarray,
        target_count: int,
    ) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Backward reduction: iteratively remove worst scenario.

        More accurate than forward selection but slower.

        O(n² * (n - target_count)) complexity
        """
        n = len(features)
        remaining = list(range(n))
        distances = cdist(features, features, metric=self.distance_metric)

        while len(remaining) > target_count:
            worst_idx = None
            best_remaining_error = float("inf")

            for candidate in remaining:
                # Tentatively remove candidate
                trial_remaining = [i for i in remaining if i != candidate]

                # Compute error without this scenario
                error = self._compute_removal_error(
                    distances, probabilities, trial_remaining, candidate
                )

                if error < best_remaining_error:
                    best_remaining_error = error
                    worst_idx = candidate

            if worst_idx is not None:
                remaining.remove(worst_idx)

        # Create mapping
        selected = remaining
        mapping = {i: [selected[i]] for i in range(len(selected))}

        for j in range(n):
            if j in selected:
                continue
            nearest = min(range(len(selected)), key=lambda i: distances[j, selected[i]])
            mapping[nearest].append(j)

        return selected, mapping

    def _compute_selection_error(
        self,
        distances: np.ndarray,
        probabilities: np.ndarray,
        selected: List[int],
        remaining: set,
    ) -> float:
        """Compute approximation error for current selection"""
        error = 0.0

        for j in remaining:
            # Distance to nearest selected scenario
            min_dist = min(distances[j, i] for i in selected)
            error += probabilities[j] * min_dist

        return error

    def _compute_removal_error(
        self,
        distances: np.ndarray,
        probabilities: np.ndarray,
        remaining: List[int],
        removed: int,
    ) -> float:
        """Compute error after removing a scenario"""
        if not remaining:
            return float("inf")

        # Find nearest remaining scenario to removed
        min_dist = min(distances[removed, i] for i in remaining)
        return probabilities[removed] * min_dist

    def _compute_wasserstein_error(
        self,
        original_features: np.ndarray,
        original_probs: np.ndarray,
        reduced_features: np.ndarray,
        reduced_probs: np.ndarray,
    ) -> float:
        """
        Compute Wasserstein distance between original and reduced distributions.

        This is the approximation error of the scenario reduction.
        Uses 1-Wasserstein (Earth Mover's Distance) approximation.
        """
        # Cost matrix: distance between each original and reduced scenario
        cost_matrix = cdist(original_features, reduced_features, metric=self.distance_metric)

        # Approximate Wasserstein by nearest-neighbor assignment
        # (exact Wasserstein would need linear programming)
        error = 0.0
        for i, p in enumerate(original_probs):
            min_cost = cost_matrix[i].min()
            error += p * min_cost

        return float(error)


def reduce_conformal_scenarios(
    scenarios: List[Scenario],
    target_count: int = 50,
    method: str = "fast_forward",
) -> List[Scenario]:
    """
    Convenience function to reduce scenarios.

    Args:
        scenarios: Original scenario list from ConformalScenarioGenerator
        target_count: Target number of scenarios
        method: Reduction method ("fast_forward", "forward_selection", "backward_reduction")

    Returns:
        Reduced scenario list with aggregated probabilities
    """
    reducer = WassersteinScenarioReducer()
    result = reducer.reduce(scenarios, target_count, method)
    return result.reduced_scenarios


def select_representative_scenarios(
    scenarios: List[Scenario],
    n_representatives: int = 5,
    method: str = "fast_forward",
) -> List[Scenario]:
    """
    Select a small number of representative scenarios for analysis.

    Useful for:
    - Scenario visualization
    - Sensitivity analysis
    - Identifying worst/best case scenarios

    Args:
        scenarios: Original scenario list
        n_representatives: Number of representative scenarios
        method: Selection method

    Returns:
        List of representative scenarios
    """
    return reduce_conformal_scenarios(scenarios, n_representatives, method)


class AdaptiveScenarioReducer:
    """
    Adaptively reduces scenarios based on error tolerance.

    Instead of specifying target count, specifies maximum acceptable
    Wasserstein error, and finds minimum number of scenarios needed.
    """

    def __init__(
        self,
        max_error: float = 0.1,
        min_scenarios: int = 10,
        max_scenarios: int = 100,
    ):
        """
        Initialize adaptive reducer.

        Args:
            max_error: Maximum acceptable Wasserstein error
            min_scenarios: Minimum number of scenarios to keep
            max_scenarios: Maximum number of scenarios to keep
        """
        self.max_error = max_error
        self.min_scenarios = min_scenarios
        self.max_scenarios = max_scenarios
        self.base_reducer = WassersteinScenarioReducer()

    def reduce(
        self,
        scenarios: List[Scenario],
        method: str = "fast_forward",
    ) -> ScenarioReductionResult:
        """
        Reduce scenarios to minimum count that satisfies error tolerance.

        Uses binary search to find optimal target count.
        """
        n = len(scenarios)

        if n <= self.min_scenarios:
            return self.base_reducer.reduce(scenarios, n, method)

        low = self.min_scenarios
        high = min(n, self.max_scenarios)

        best_result = None

        while low < high:
            mid = (low + high) // 2
            result = self.base_reducer.reduce(scenarios, mid, method)

            if result.wasserstein_error <= self.max_error:
                best_result = result
                high = mid
            else:
                low = mid + 1

        if best_result is None:
            # Error tolerance not achievable, return max scenarios
            best_result = self.base_reducer.reduce(scenarios, self.max_scenarios, method)

        logger.info(
            f"Adaptive reduction: {n} -> {best_result.reduced_count} scenarios "
            f"(error={best_result.wasserstein_error:.4f}, target<={self.max_error})"
        )

        return best_result
