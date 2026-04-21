# Hierarchy drilldown (TMS)

All views (Movement Plan, Analytics, Transportation Plan, Decision
Stream) use breadcrumb navigation with drilldown.

## Geography hierarchy

- Source: AWS SC DM `geography` table with `parent_geo_id` tree.
- **Includes serving lanes** — facility hierarchy includes every
  lane that connects a facility to origins / destinations.
- Breadcrumb: Region → Country → State → Metro → Facility.

## Commodity hierarchy

- Freight-class tree: Class → Subclass → Commodity.
- Tenant-sourced — no hardcoded freight classes.

## Carrier hierarchy

- Carrier portfolio: Mode → Carrier → Service Level.
- Example: Road → CarrierName → (FTL, LTL, Parcel).

## Cross-cutting

- All three breadcrumbs drive filtering identically across Movement
  Plan, Analytics, Transportation Plan, and Decision Stream.
- Missing hierarchy node → error, not a silent default. See
  [no-fallbacks.md](no-fallbacks.md).
