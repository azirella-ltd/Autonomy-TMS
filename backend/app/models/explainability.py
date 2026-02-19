"""
Explainability Level Enum

Defines verbosity levels for AI agent explanations.
Can be set at group level with user-level overrides.
"""

from enum import Enum


class ExplainabilityLevel(str, Enum):
    """
    Verbosity level for AI agent explanations.

    - VERBOSE: Detailed multi-paragraph explanations with examples, context, and reasoning steps
    - NORMAL: Balanced explanations with key reasoning and context (default)
    - SUCCINCT: Brief one-sentence summaries focusing on the recommendation only
    """
    VERBOSE = "VERBOSE"
    NORMAL = "NORMAL"
    SUCCINCT = "SUCCINCT"
