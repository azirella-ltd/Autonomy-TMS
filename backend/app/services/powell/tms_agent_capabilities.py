"""Re-export shim — pure logic now in Core.

TMS agent capability declarations live in
`azirella_data_model.powell.tms.agent_capabilities`. Re-exported here
to preserve the legacy import path
`from app.services.powell.tms_agent_capabilities import ...`.
"""
from azirella_data_model.powell.tms.agent_capabilities import *  # noqa: F401,F403
from azirella_data_model.powell.tms.agent_capabilities import (  # noqa: F401
    TMS_TRM_CAPABILITIES,
    AgentCapabilities,
)
