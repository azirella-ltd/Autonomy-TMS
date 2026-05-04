"""autonomy-tms-mcp-adapters — TMS vendor MCP adapters (AD-12 THIRD_PARTY tier).

Each vendor (SAP TM, Manhattan TM, Oracle OTM, MercuryGate, BlueYonder TMS)
ships as a sub-package under ``autonomy_tms_mcp_adapters.<vendor>``. Each
sub-package's ``__init__.py`` exposes ``get_adapter_bundle()`` which returns
an :class:`MCPAdapterBundle` consumed by ``azirella-router``.

Entry-point registration (in pyproject.toml) per vendor:

.. code-block:: toml

    [project.entry-points."azirella_router.mcp_adapters"]
    tms_sap_tm = "autonomy_tms_mcp_adapters.sap_tm:get_adapter_bundle"

v0.1.0 status
-------------

**Skeleton only.** No vendor adapters ship yet. This package establishes
the home so the first adapter (likely SAP TM, post-2026-05-11 demo) lands
in the right place. The Microsoft demo runs entirely on AZIRELLA + HEURISTIC
tiers; THIRD_PARTY isn't on the demo path.

Each vendor adapter that lands MUST:

- Match the canonical TMS skill IDs (``transport.lane.estimate_eta`` etc.).
- Use ``azirella_heuristics_common.stamp_heuristic_response`` semantics
  but with ``producer_tier="THIRD_PARTY"`` and a vendor-specific
  ``producer_signature`` — the helper's tier label is parameterised in
  v0.2.0 (currently ``"HEURISTIC"`` only); until then the adapter
  stamps responses manually.
- Translate the Azirella-canonical input dict to the vendor's protocol
  (REST, MCP server, SOAP) and translate the response back to the
  canonical output shape.
- Implement timeouts + retries appropriate for the vendor.
"""

__version__ = "0.1.0"
