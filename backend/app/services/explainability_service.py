"""
Explainability Service

Provides interpretability and explainability for AI/ML models:
- LIME (Local Interpretable Model-agnostic Explanations)
- Attention weight visualization for GNN models
- Feature importance analysis
- Decision path tracing
- Counterfactual explanations
"""

from typing import Dict, Any, List, Optional, Tuple, Callable
import logging
import json
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import lime
    import lime.lime_tabular
    LIME_AVAILABLE = True
except ImportError:
    LIME_AVAILABLE = False
    lime = None

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


class ExplainabilityService:
    """
    Service for explaining model predictions and decisions.

    Supports:
    - LIME explanations for any model
    - Attention weight extraction for GNN models
    - Feature importance ranking
    - Natural language explanations
    """

    def __init__(self):
        self.background_data: Optional[np.ndarray] = None
        self.feature_names: Optional[List[str]] = None
        self.lime_explainer: Optional[Any] = None

    def set_background_data(self, data: np.ndarray, feature_names: List[str]):
        """
        Set background data for LIME explainer.

        Args:
            data: Background dataset [num_samples, num_features]
            feature_names: Names of features
        """
        self.background_data = data
        self.feature_names = feature_names

        if LIME_AVAILABLE:
            self.lime_explainer = lime.lime_tabular.LimeTabularExplainer(
                training_data=data,
                feature_names=feature_names,
                mode='regression',
                discretize_continuous=False
            )
            logger.info(f"LIME explainer initialized with {len(feature_names)} features")

    async def explain_with_lime(
        self,
        model: Callable,
        input_features: np.ndarray,
        num_features: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate LIME explanation for a model prediction.

        Args:
            model: Prediction function (input -> output)
            input_features: Input features to explain [num_features]
            num_features: Number of top features to include (default: all)

        Returns:
            explanation: LIME explanation with feature importances
        """
        if not LIME_AVAILABLE:
            raise RuntimeError("LIME is not available. Install with: pip install lime")

        if self.lime_explainer is None:
            raise RuntimeError("LIME explainer not initialized. Call set_background_data() first.")

        num_features = num_features or len(self.feature_names)

        # Generate explanation
        explanation = self.lime_explainer.explain_instance(
            input_features,
            model,
            num_features=num_features
        )

        # Extract feature importances
        feature_importance = dict(explanation.as_list())

        # Get prediction
        prediction = model(input_features.reshape(1, -1))[0]

        # Generate natural language explanation
        nl_explanation = self._generate_natural_language_explanation(
            feature_importance,
            prediction
        )

        return {
            "method": "LIME",
            "prediction": float(prediction),
            "feature_importance": feature_importance,
            "top_features": self._get_top_features(feature_importance, top_k=5),
            "explanation": nl_explanation,
            "intercept": float(explanation.intercept[0]) if hasattr(explanation, 'intercept') else None,
            "r2_score": float(explanation.score) if hasattr(explanation, 'score') else None
        }

    def _generate_natural_language_explanation(
        self,
        feature_importance: Dict[str, float],
        prediction: float
    ) -> str:
        """Generate human-readable explanation."""
        # Sort features by absolute importance
        sorted_features = sorted(
            feature_importance.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )

        if not sorted_features:
            return f"Predicted order quantity: {prediction:.1f} units"

        # Generate explanation
        parts = [f"Predicted order quantity: {prediction:.1f} units."]

        # Most influential factors
        top_positive = [f for f, imp in sorted_features if imp > 0][:2]
        top_negative = [f for f, imp in sorted_features if imp < 0][:2]

        if top_positive:
            parts.append(f"Increased by: {', '.join(top_positive)}.")

        if top_negative:
            parts.append(f"Decreased by: {', '.join(top_negative)}.")

        return " ".join(parts)

    def _get_top_features(
        self,
        feature_importance: Dict[str, float],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top K most important features."""
        sorted_features = sorted(
            feature_importance.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:top_k]

        return [
            {
                "feature": feature,
                "importance": float(importance),
                "direction": "increase" if importance > 0 else "decrease"
            }
            for feature, importance in sorted_features
        ]

    async def explain_gnn_prediction(
        self,
        model: nn.Module,
        node_features: np.ndarray,
        edge_index: np.ndarray,
        node_id: int,
        feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Explain GNN prediction with attention weights and feature importance.

        Args:
            model: GNN model
            node_features: Node features [num_nodes, num_features]
            edge_index: Edge indices [2, num_edges]
            node_id: Target node to explain
            feature_names: Feature names

        Returns:
            explanation: GNN-specific explanation with attention weights
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is required for GNN explanations")

        model.eval()

        # Convert to tensors
        x = torch.tensor(node_features, dtype=torch.float32)
        edge_idx = torch.tensor(edge_index, dtype=torch.long)

        with torch.no_grad():
            # Forward pass
            if hasattr(model, 'forward'):
                output = model(x, edge_idx)
            else:
                output = model(x)

            # Extract prediction for target node
            if isinstance(output, dict):
                prediction = output.get('order', output.get('embeddings'))
            else:
                prediction = output

            if prediction.ndim > 1:
                node_prediction = prediction[node_id]
            else:
                node_prediction = prediction

        # Extract attention weights if available
        attention_weights = None
        if hasattr(model, 'get_attention_weights'):
            attention_weights = model.get_attention_weights(x, edge_idx)
        elif hasattr(model, 'convs'):
            # Try to extract attention from GAT layers
            for conv in model.convs:
                if hasattr(conv, 'alpha'):
                    attention_weights = conv.alpha
                    break

        explanation = {
            "method": "GNN_Attention",
            "node_id": node_id,
            "prediction": float(node_prediction.mean()) if node_prediction.numel() > 1 else float(node_prediction),
            "node_features": {
                feature_names[i]: float(node_features[node_id, i])
                for i in range(len(feature_names))
            }
        }

        # Add attention weights if available
        if attention_weights is not None:
            explanation["attention_weights"] = self._process_attention_weights(
                attention_weights,
                edge_index,
                node_id
            )
            explanation["attention_explanation"] = self._explain_attention(
                attention_weights,
                edge_index,
                node_id
            )

        # Feature importance via gradient-based method
        if hasattr(model, 'requires_grad') and model.training:
            feature_importance = self._compute_gradient_based_importance(
                model,
                x,
                edge_idx,
                node_id
            )
            explanation["feature_importance"] = {
                feature_names[i]: float(feature_importance[i])
                for i in range(len(feature_names))
            }

        return explanation

    def _process_attention_weights(
        self,
        attention: torch.Tensor,
        edge_index: np.ndarray,
        target_node: int
    ) -> Dict[str, Any]:
        """Process attention weights for target node."""
        # Find edges connected to target node
        incoming_edges = np.where(edge_index[1] == target_node)[0]

        if len(incoming_edges) == 0:
            return {"incoming_attention": {}}

        # Extract attention for incoming edges
        attention_np = attention.cpu().numpy() if isinstance(attention, torch.Tensor) else attention

        incoming_attention = {}
        for edge_idx in incoming_edges:
            source_node = int(edge_index[0, edge_idx])
            attention_value = float(attention_np[edge_idx]) if attention_np.ndim == 1 else float(attention_np[edge_idx].mean())
            incoming_attention[f"node_{source_node}"] = attention_value

        return {
            "incoming_attention": incoming_attention,
            "num_neighbors": len(incoming_edges),
            "max_attention": max(incoming_attention.values()) if incoming_attention else 0.0,
            "mean_attention": np.mean(list(incoming_attention.values())) if incoming_attention else 0.0
        }

    def _explain_attention(
        self,
        attention: torch.Tensor,
        edge_index: np.ndarray,
        target_node: int
    ) -> str:
        """Generate natural language explanation of attention."""
        incoming_edges = np.where(edge_index[1] == target_node)[0]

        if len(incoming_edges) == 0:
            return "Node has no incoming connections."

        attention_np = attention.cpu().numpy() if isinstance(attention, torch.Tensor) else attention

        # Find most attended neighbors
        neighbor_attention = []
        for edge_idx in incoming_edges:
            source_node = int(edge_index[0, edge_idx])
            attention_value = float(attention_np[edge_idx]) if attention_np.ndim == 1 else float(attention_np[edge_idx].mean())
            neighbor_attention.append((source_node, attention_value))

        neighbor_attention.sort(key=lambda x: x[1], reverse=True)

        # Generate explanation
        top_neighbor, top_attention = neighbor_attention[0]
        explanation = f"Most influenced by node {top_neighbor} (attention: {top_attention:.3f}). "

        if len(neighbor_attention) > 1:
            other_neighbors = len(neighbor_attention) - 1
            explanation += f"Also considering {other_neighbors} other neighbor(s)."

        return explanation

    def _compute_gradient_based_importance(
        self,
        model: nn.Module,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        node_id: int
    ) -> np.ndarray:
        """Compute feature importance using gradients."""
        x_with_grad = x.clone().detach().requires_grad_(True)

        # Forward pass
        output = model(x_with_grad, edge_index)

        if isinstance(output, dict):
            prediction = output.get('order', output.get('embeddings'))
        else:
            prediction = output

        # Extract target node prediction
        if prediction.ndim > 1:
            target_pred = prediction[node_id].sum()
        else:
            target_pred = prediction.sum()

        # Backward pass
        target_pred.backward()

        # Feature importance = absolute gradient * feature value
        gradients = x_with_grad.grad[node_id].cpu().numpy()
        feature_values = x[node_id].cpu().numpy()
        importance = np.abs(gradients * feature_values)

        return importance

    async def generate_counterfactual(
        self,
        model: Callable,
        input_features: np.ndarray,
        target_change: float,
        feature_constraints: Optional[Dict[str, Tuple[float, float]]] = None,
        max_iterations: int = 100
    ) -> Dict[str, Any]:
        """
        Generate counterfactual explanation.

        Find minimal changes to input that achieve target prediction change.

        Args:
            model: Prediction function
            input_features: Original input [num_features]
            target_change: Desired change in prediction
            feature_constraints: Min/max bounds for each feature
            max_iterations: Maximum optimization iterations

        Returns:
            counterfactual: Modified input and explanation
        """
        original_prediction = model(input_features.reshape(1, -1))[0]
        target_prediction = original_prediction + target_change

        # Simple gradient-free search
        best_features = input_features.copy()
        best_distance = float('inf')

        for iteration in range(max_iterations):
            # Random perturbation
            perturbation = np.random.randn(len(input_features)) * 0.1
            candidate_features = input_features + perturbation

            # Apply constraints
            if feature_constraints:
                for i, feature_name in enumerate(self.feature_names):
                    if feature_name in feature_constraints:
                        min_val, max_val = feature_constraints[feature_name]
                        candidate_features[i] = np.clip(candidate_features[i], min_val, max_val)

            # Evaluate
            candidate_prediction = model(candidate_features.reshape(1, -1))[0]

            # Check if closer to target
            distance_to_target = abs(candidate_prediction - target_prediction)
            feature_distance = np.linalg.norm(candidate_features - input_features)

            if distance_to_target < abs(target_change * 0.1) and feature_distance < best_distance:
                best_features = candidate_features
                best_distance = feature_distance

        final_prediction = model(best_features.reshape(1, -1))[0]

        # Calculate changes
        feature_changes = {
            self.feature_names[i]: {
                "original": float(input_features[i]),
                "counterfactual": float(best_features[i]),
                "change": float(best_features[i] - input_features[i]),
                "percent_change": float((best_features[i] - input_features[i]) / input_features[i] * 100) if input_features[i] != 0 else 0
            }
            for i in range(len(input_features))
            if abs(best_features[i] - input_features[i]) > 0.01
        }

        return {
            "method": "Counterfactual",
            "original_prediction": float(original_prediction),
            "target_prediction": float(target_prediction),
            "achieved_prediction": float(final_prediction),
            "feature_changes": feature_changes,
            "total_change": float(best_distance),
            "success": abs(final_prediction - target_prediction) < abs(target_change * 0.2),
            "explanation": self._generate_counterfactual_explanation(
                feature_changes,
                original_prediction,
                final_prediction
            )
        }

    def _generate_counterfactual_explanation(
        self,
        feature_changes: Dict[str, Dict[str, float]],
        original_prediction: float,
        final_prediction: float
    ) -> str:
        """Generate natural language counterfactual explanation."""
        if not feature_changes:
            return "No significant changes needed to achieve target prediction."

        # Sort by absolute change
        sorted_changes = sorted(
            feature_changes.items(),
            key=lambda x: abs(x[1]['change']),
            reverse=True
        )[:3]

        explanation_parts = [
            f"To change prediction from {original_prediction:.1f} to {final_prediction:.1f}:"
        ]

        for feature, change_info in sorted_changes:
            if change_info['change'] > 0:
                explanation_parts.append(
                    f"Increase {feature} by {change_info['percent_change']:.1f}%"
                )
            else:
                explanation_parts.append(
                    f"Decrease {feature} by {abs(change_info['percent_change']):.1f}%"
                )

        return ". ".join(explanation_parts) + "."

    def save_explanation(self, explanation: Dict[str, Any], output_path: str):
        """Save explanation to JSON file."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(explanation, f, indent=2)

        logger.info(f"Saved explanation to {output_path}")


class ShapleyValueExplainer:
    """
    Shapley value-based explanations (simplified implementation).

    Computes feature contributions based on cooperative game theory.
    """

    def __init__(self, model: Callable, background_data: np.ndarray):
        self.model = model
        self.background_data = background_data

    def explain(
        self,
        input_features: np.ndarray,
        num_samples: int = 100
    ) -> Dict[str, float]:
        """
        Compute Shapley values for input features.

        Args:
            input_features: Input to explain [num_features]
            num_samples: Number of Monte Carlo samples

        Returns:
            shapley_values: Feature contributions
        """
        num_features = len(input_features)
        shapley_values = np.zeros(num_features)

        # Monte Carlo estimation of Shapley values
        for _ in range(num_samples):
            # Random feature ordering
            feature_order = np.random.permutation(num_features)

            # Build coalition incrementally
            coalition = np.zeros(num_features, dtype=bool)
            previous_prediction = self.model(
                self._create_masked_input(input_features, coalition).reshape(1, -1)
            )[0]

            for feature_idx in feature_order:
                # Add feature to coalition
                coalition[feature_idx] = True

                # Compute marginal contribution
                current_prediction = self.model(
                    self._create_masked_input(input_features, coalition).reshape(1, -1)
                )[0]

                marginal_contribution = current_prediction - previous_prediction
                shapley_values[feature_idx] += marginal_contribution

                previous_prediction = current_prediction

        # Average over samples
        shapley_values /= num_samples

        return {f"feature_{i}": float(shapley_values[i]) for i in range(num_features)}

    def _create_masked_input(
        self,
        input_features: np.ndarray,
        mask: np.ndarray
    ) -> np.ndarray:
        """Create input with features masked by background values."""
        # Sample background value
        background_sample = self.background_data[np.random.randint(len(self.background_data))]

        # Mask features
        masked_input = np.where(mask, input_features, background_sample)

        return masked_input
