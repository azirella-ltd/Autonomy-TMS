# Reseed Hook: SCP Food Dist → TMS Overlay

When **SCP Food Dist Demo** is reseeded, the TMS Food Dist overlay must be
re-extracted and regenerated, or it will reference stale SCP IDs (sites,
shipments, lanes, products).

## Recommended banner for SCP-side seed scripts

Add the following banner to the docstring of every SCP script that
re-creates Food Dist data (`seed_food_dist_demo.py`, `_hierarchies.py`,
`_planning_data.py`, `_transactions.py`):

```
# ─────────────────────────────────────────────────────────────────────
#  ⚠  TMS RESEED REQUIRED
# ─────────────────────────────────────────────────────────────────────
#  After running this script against SCP, the TMS Food Dist overlay
#  must be re-extracted and regenerated:
#
#     # On the TMS host (or backend container with SCP_DB_URL set):
#     python scripts/extract_scp_food_dist.py
#     python scripts/seed_food_dist_tms.py --seed-only
#     python scripts/seed_food_dist_tms.py --start <DATE> --end <DATE>
#
#  Otherwise the TMS overlay's tms_src_scp_* staging is stale and its
#  Loads/Tenders/TrackingEvents reference SCP IDs that no longer exist.
# ─────────────────────────────────────────────────────────────────────
```

## Future automation options

1. **Post-seed git hook on SCP** — invoke a webhook that triggers the TMS
   extractor + overlay rerun (requires HTTP endpoint on TMS).
2. **Dependency manifest** — TMS extractor records the SCP `snapshot_at`
   timestamps; overlay refuses to run if staging is older than a configurable
   threshold or if SCP's reported config-version is newer.
3. **Cron** — nightly extractor + overlay refresh on the TMS host (cheap if
   SCP and TMS are co-located).

For now, manual trigger via the banner is the agreed pattern (per
2026-04-14 decision). See [project_food_dist_tms_etl.md](../../../.claude/projects/-home-trevor-Autonomy-TMS/memory/project_food_dist_tms_etl.md).
