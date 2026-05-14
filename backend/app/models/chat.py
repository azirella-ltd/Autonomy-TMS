"""TMS chat shim — re-exports canonical from Core.

The canonical `ChatMessage`, `AgentSuggestion`, `WhatIfAnalysis` plus
the `MessageType` and `SenderType` enums live in
`azirella_data_model.simulation.chat` (promoted 2026-05-14 per
MIGRATION_REGISTER §3.73 Step 3). Both SCP and TMS carried
byte-identical copies before promotion (md5 f928b0a4).

The back-relations on `Scenario` and `ScenarioUser` also moved to
Core; the plane-side monkey-patches for those attributes have been
removed.
"""
from azirella_data_model.simulation.chat import (  # noqa: F401
    AgentSuggestion,
    ChatMessage,
    MessageType,
    SenderType,
    WhatIfAnalysis,
)


__all__ = [
    "AgentSuggestion",
    "ChatMessage",
    "MessageType",
    "SenderType",
    "WhatIfAnalysis",
]
