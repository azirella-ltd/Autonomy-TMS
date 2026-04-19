"""Re-export shim — pure logic now in Core.

Facility-type → active-TRM mapping lives in
`azirella_data_model.powell.tms.site_capabilities`.
"""
from azirella_data_model.powell.tms.site_capabilities import *  # noqa: F401,F403
from azirella_data_model.powell.tms.site_capabilities import (  # noqa: F401
    get_active_tms_trms,
)
