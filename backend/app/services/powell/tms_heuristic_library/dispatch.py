"""Re-export shim — pure logic now in Core.

TMS heuristic dispatcher lives in
`azirella_data_model.powell.tms.heuristic_library.dispatch`.
"""
from azirella_data_model.powell.tms.heuristic_library.dispatch import *  # noqa: F401,F403
from azirella_data_model.powell.tms.heuristic_library.dispatch import (  # noqa: F401
    compute_tms_decision,
)
