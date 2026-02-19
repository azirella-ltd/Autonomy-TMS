# AWS Supply Chain - Complete Data Model Documentation

**Compiled:** 2026-01-09
**Source:** AWS Supply Chain User Guide

This comprehensive data dictionary documents all AWS Supply Chain entities with complete field specifications, data types, relationships, and constraints.

---

## Table of Contents

### Organization Entities
1. [company](#company)
2. [geography](#geography)
3. [trading_partner](#trading_partner)

### Network Entities
4. [site](#site)
5. [transportation_lane](#transportation_lane)

### Product Entities
6. [product](#product)
7. [product_hierarchy](#product_hierarchy)

### Supply Planning Entities
8. [sourcing_rules](#sourcing_rules)
9. [sourcing_schedule](#sourcing_schedule)
10. [sourcing_schedule_details](#sourcing_schedule_details)
11. [inv_policy](#inv_policy)
12. [inv_level](#inv_level)
13. [vendor_product](#vendor_product)
14. [vendor_lead_time](#vendor_lead_time)
15. [supply_planning_parameters](#supply_planning_parameters)

### Manufacturing Entities
16. [product_bom](#product_bom)
17. [production_process](#production_process)

### Inbound Order Entities
18. [inbound_order](#inbound_order)
19. [inbound_order_line](#inbound_order_line)
20. [inbound_order_line_schedule](#inbound_order_line_schedule)

### Shipment Entities
21. [shipment](#shipment)
22. [shipment_stop](#shipment_stop)
23. [shipment_lot](#shipment_lot)

### Outbound Fulfillment Entities
24. [outbound_order_line](#outbound_order_line)
25. [outbound_shipment](#outbound_shipment)

### Planning Output Entities
26. [supply_plan](#supply_plan)
27. [reservation](#reservation)

### Forecast Entities
28. [forecast](#forecast)
29. [supplementary_time_series](#supplementary_time_series)

### Operations Entities
30. [process_header](#process_header)
31. [process_operation](#process_operation)
32. [process_product](#process_product)
33. [work_order_plan](#work_order_plan)

### Cost Management Entities
34. [customer_cost](#customer_cost)

### Segmentation Entities
35. [segmentation](#segmentation)

---

## Global Constraints & Standards

### Data Type Formats
- **Timestamps**: All timestamp fields must be in **ISO 8601 format**
- **Strings**: Support only specific special characters: `# $ % - . / ^ _ { }`

### Default Values (SAP/EDI Ingestion)
- **String fields**: `SCN_RESERVED_NO_VALUE_PROVIDED`
- **Start dates**: `1900-01-01 00:00:00`
- **End dates**: `9999-12-31 23:59:59`

### Deletion Flags
- **is_deleted**: `"true"` (deleted/excluded) or `"false"` (active/included)
- **is_active**: `"true"` (active) or `"false"` (inactive)
- **Blank/null behavior varies by entity** - check specific entity rules

---

## Organization Entities

### <a name="company"></a>1. company

**Purpose**: Defines company/organization information

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Company identifier |
| description | string | No | Company description |
| address_1 | string | No | Address line 1 |
| address_2 | string | No | Address line 2 |
| address_3 | string | No | Address line 3 |
| city | string | No | City |
| state_prov | string | No | State/province |
| postal_code | string | No | Postal code |
| country | string | No | Country |
| phone_number | string | No | Phone number |
| time_zone | string | No | Time zone |
| calendar_id | string | No | Calendar identifier |

---

### <a name="geography"></a>2. geography

**Purpose**: Defines geographical hierarchies for regional planning and filtering

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Geographical ID (referenced as geo_id or region_id) |
| description | string | No | Geographical location |
| company_id | string | No | Company ID (FK) |
| parent_geo_id | string | No | Parent geographical ID for hierarchical structure (FK) |
| address_1 | string | No | Address line 1 |
| address_2 | string | No | Address line 2 |
| address_3 | string | No | Address line 3 |
| city | string | No | City corresponding to this geo-region |
| state_prov | string | No | State corresponding to this geo-region |
| postal_code | string | No | Postal code |
| country | string | No | Country |
| phone_number | string | No | Contact number |
| time_zone | string | No | Local time zone |
| source | string | No | Source of data |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| parent_geo_id | geography | id |

#### Constraints
- **Hierarchical Structure**: NULL `parent_geo_id` indicates top-level region

---

### <a name="trading_partner"></a>3. trading_partner

**Purpose**: Defines suppliers, customers, carriers, and other trading partners

#### Primary Key (Composite)
- `id` + `tpartner_type` + `geo_id` + `eff_start_date` + `eff_end_date`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Partner ID (referenced as tpartner_id) |
| tpartner_type | string | Yes | Type: vendor, channel partner, 3PL, etc. |
| geo_id | string | Yes | Region associated with partner (FK) |
| eff_start_date | timestamp | Yes | Relationship start timestamp |
| eff_end_date | timestamp | Yes | Relationship end timestamp |
| description | string | No | Partner description |
| company_id | string | No | Company ID (FK) |
| is_active | string | No | Active status flag |
| address_1 | string | No | Address line 1 |
| address_2 | string | No | Address line 2 |
| address_3 | string | No | Address line 3 |
| city | string | No | City |
| state_prov | string | No | State/province |
| postal_code | string | No | Postal code |
| country | string | No | Country |
| phone_number | string | No | Contact phone |
| time_zone | string | No | Local time zone |
| latitude | double | No | Latitude |
| longitude | double | No | Longitude |
| os_id | string | No | Open Supplier Hub organizational ID |
| duns_number | string | No | Dun & Bradstreet 9-digit ID |
| source | string | No | Data source |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| geo_id | geography | id |

#### Validation Rules
- **For suppliers**: Set `tpartner_type = "Vendor"`
- **Default dates**: If unknown, use `1900-01-01 00:00:00` to `9999-12-31 23:59:59`

---

## Network Entities

### <a name="site"></a>4. site

**Purpose**: Defines physical locations (warehouses, factories, stores, DCs)

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Site identifier |
| description | string | No | Site description |
| company_id | string | No | Company ID (FK) |
| geo_id | string | No | Geography hierarchy ID (FK) |
| address_1 | string | No | Site address line 1 |
| address_2 | string | No | Site address line 2 |
| address_3 | string | No | Site address line 3 |
| city | string | No | City |
| state_prov | string | No | State/province |
| postal_code | string | No | Postal code |
| country | string | No | Country |
| phone_number | string | No | Contact number |
| email | string | No | Point of contact email |
| time_zone | string | No | Local time zone |
| site_type | string | No | Type: warehouse, delivery station, factory, store |
| unlocode | string | No | UN/LOCODE standardized code |
| latitude | double | No | Latitude |
| longitude | double | No | Longitude |
| is_active | string | No | Active status: "true" or "false" |
| site_calendar_id | string | No | Operating/holiday calendar (FK) |
| site_classifier | string | No | Classification (e.g., "high foot fall store") |
| open_date | timestamp | No | Site opening date |
| end_date | timestamp | No | Site closing date |
| source | string | No | Data source |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| geo_id | geography | id |
| site_calendar_id | calendar | calendar_id |

#### Validation Rules
- **Planning inclusion**: `is_active = False` excludes site from planning; blank/null = include

---

### <a name="transportation_lane"></a>5. transportation_lane

**Purpose**: Defines transfer routes between sites with transit time and cost

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Transportation lane identifier |
| from_site_id | string | Yes | Origin site ID (FK) |
| to_site_id | string | Yes | Destination site ID (FK) |
| product_group_id | string | Yes | Product group (FK) |
| transit_time | numeric | Yes | Transit time duration |
| time_uom | string | Yes | Time unit of measure (supported: "Day") |
| distance | numeric | No | Distance between sites |
| distance_uom | string | No | Distance unit of measure |
| eff_start_date | date | No | Effective start date |
| eff_end_date | date | No | Effective end date |
| product_id | string | No | Specific product (optional override) (FK) |
| emissions_per_unit | numeric | No | CO2 emissions per unit |
| emissions_per_weight | numeric | No | CO2 emissions per weight unit |
| company_id | string | No | Company identifier (FK) |
| from_geo_id | string | Yes | Origin geography (FK). Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| to_geo_id | string | Yes | Destination geography (FK). Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| carrier_tpartner_id | string | Yes | Carrier trading partner (FK). Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| service_type | string | Yes | Transportation service type. Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| trans_mode | string | Yes | Transportation mode. Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| cost_per_unit | numeric | No | Cost per transportation unit |
| cost_currency | string | No | Currency code |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| from_site_id | site | id |
| to_site_id | site | id |
| product_group_id | product_hierarchy | id |
| product_id | product | id |
| company_id | company | id |
| from_geo_id | geography | id |
| to_geo_id | geography | id |
| carrier_tpartner_id | trading_partner | id |

---

## Product Entities

### <a name="product"></a>6. product

**Purpose**: Defines individual products/items/SKUs

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Product ID (referenced as product_id) |
| description | string | Yes | Product description |
| company_id | string | No | Company ID (FK) |
| product_group_id | string | No | Product group ID (FK) |
| product_type | string | No | Type: finished good, component, service, packaging |
| hts_code | string | No | Harmonized Tariff Schedule code |
| is_hazmat | string | No | Hazmat compliant flag |
| is_flammable | string | No | Flammable indicator |
| is_special_handling | string | No | Special handling required |
| is_perishable | string | No | Perishable indicator |
| is_digital | string | No | Digital product indicator |
| is_deleted | string | No | Deleted status: "true" (excluded) or "false" (included) |
| is_lot_controlled | string | No | Lot control indicator |
| is_expiry_controlled | string | No | Expiry date control indicator |
| creation_date | timestamp | No | Product launch date |
| brand_name | string | No | Brand name |
| parent_product_id | string | No | Parent product ID for bundles (FK) |
| display_desc | string | No | External description |
| discontinue_day | timestamp | No | Discontinuation date |
| base_uom | string | No | Base unit of measure. Default: "Eaches" |
| unit_cost | double | No | Average unit cost (currency_uom per base_uom) |
| unit_price | double | No | Unit price / MSRP |
| inventory_holding_cost | double | No | Average yearly holding cost |
| currency_uom | string | No | Currency unit of measure |
| product_available_day | timestamp | No | Available for fulfillment date |
| shipping_weight | double | No | Default carrier weight |
| shipping_dimension | double | No | Dimensional weight for carrier |
| unit_volume | double | No | Volume per base_uom |
| pkg_length | double | No | Package length |
| pkg_width | double | No | Package width |
| pkg_height | double | No | Package height |
| weight_uom | string | No | Weight unit of measure |
| dim_uom | string | No | Dimension unit of measure |
| volume_uom | string | No | Volume unit of measure |
| diameter | double | No | Product diameter |
| color | string | No | Product color |
| casepack_size | int | No | Products per casepack |
| gtin | string | No | Global Trade Item Number (14-digit) |
| long_term_horizon | double | No | Time window for salvage value |
| long_term_horizon_uom | string | No | Long term horizon UOM |
| salvage_value_percentage | double | No | Cost recovery percentage at end of horizon |
| sap_0material_attr__prdha | string | No | SAP product hierarchy predicate key |
| shelf_life | double | No | Storage duration before spoilage |
| shelf_life_uom | string | No | Shelf life unit of measure |
| un_id | string | No | UN ID for dangerous goods (4-digit) (FK) |
| demand_planning_enabled | string | No | Demand planning flag |
| inventory_planning_enabled | string | No | Inventory planning flag |
| mrp_enabled | string | No | MRP planning flag |
| purchased_item | string | No | Purchased item flag |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_group_id | product_hierarchy | id |
| parent_product_id | product | id |
| un_id | un_details | un_id |

#### Validation Rules
- **is_deleted**: Blank/null defaults to `True` (exclude); set `False` to include in planning
- **un_id constraint**: If populated, `is_hazmat` must be `"true"`
- **base_uom default**: "Eaches"

---

### <a name="product_hierarchy"></a>7. product_hierarchy

**Purpose**: Defines product groups for categorization and filtering

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Product group ID |
| description | string | No | Product group description (e.g., "dairy", "clothes") |
| company_id | string | No | Company ID (FK) |
| parent_product_group_id | string | No | Parent group for multi-level hierarchies (FK) |
| creation_date | timestamp | No | Group creation date |
| update_date | timestamp | No | Group update date |
| source | string | No | Data source |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| parent_product_group_id | product_hierarchy | id |

#### Constraints
- **Hierarchical Structure**: Supports nested groups via `parent_product_group_id`
- **Top-level groups**: NULL `parent_product_group_id`

---

## Supply Planning Entities

### <a name="sourcing_rules"></a>8. sourcing_rules

**Purpose**: Defines supply chain network topology (how products are sourced)

#### Primary Key
- `sourcing_rule_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| sourcing_rule_id | string | Yes | Rule identifier |
| company_id | string | No | Company ID (FK) |
| product_id | string | No | Product ID (FK) - either product_id or product_group_id required |
| product_group_id | string | No | Product group (FK) - either product_id or product_group_id required |
| from_site_id | string | No | Source site (FK) - required for type `transfer` |
| to_site_id | string | Yes | Destination site (FK) |
| sourcing_rule_type | string | Yes | Rule type: `transfer`, `buy`, `manufacture` (lowercase only) |
| tpartner_id | string | No | Trading partner (FK) - required for type `buy` |
| transportation_lane_id | string | No | Transportation lane (FK) - required for type `transfer` |
| production_process_id | string | No | Production process (FK) - required for type `manufacture` |
| sourcing_priority | numeric | No | Priority ranking (lower number = higher priority) |
| min_qty | numeric | No | Minimum order quantity |
| max_qty | numeric | No | Maximum order quantity |
| qty_multiple | numeric | No | Order quantity multiple |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| product_group_id | product_hierarchy | id |
| from_site_id | site | id |
| to_site_id | site | id |
| tpartner_id | trading_partner | id |
| transportation_lane_id | transportation_lane | id |
| production_process_id | production_process | production_process_id |

#### Validation Rules
- **sourcing_rule_type**: Must be lowercase: `transfer`, `buy`, or `manufacture`
- **Conditional requirements**:
  - Type `transfer`: Requires `from_site_id` and `transportation_lane_id`
  - Type `buy`: Requires `tpartner_id`
  - Type `manufacture`: Requires `production_process_id`
- **Override logic**: `product_id` > `product_group_id` > `company_id`

---

### <a name="sourcing_schedule"></a>9. sourcing_schedule

**Purpose**: Generates purchase/transfer plans based on schedules (optional)

#### Primary Key
- `sourcing_schedule_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| sourcing_schedule_id | string | Yes | Schedule identifier |
| company_id | string | No | Company ID (FK) |
| tpartner_id | string | No | Trading partner (FK) - required for type `InboundOrdering` |
| status | string | Yes | Schedule status |
| from_site_id | string | No | Source site (FK) - required for type `OutboundShipping` |
| to_site_id | string | Yes | Destination site (FK) |
| schedule_type | string | Yes | Type: `InboundOrdering` or `OutboundShipping` |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| tpartner_id | trading_partner | id |
| from_site_id | site | id |
| to_site_id | site | id |

---

### <a name="sourcing_schedule_details"></a>10. sourcing_schedule_details

**Purpose**: Schedule-line level details for sourcing schedules (optional)

#### Primary Key
- `sourcing_schedule_detail_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| sourcing_schedule_detail_id | string | Yes | Detail identifier |
| sourcing_schedule_id | string | Yes | Parent schedule ID (FK) |
| company_id | string | No | Company ID (FK) |
| product_id | string | No | Product (FK) - either product_id or product_group_id required |
| product_group_id | string | No | Product group (FK) - either product_id or product_group_id required |
| day_of_week | string | No | Day of week (0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat) |
| week_of_month | string | No | Week of month |
| time_of_day | string | No | Time of day |
| date | date | No | Specific date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| sourcing_schedule_id | sourcing_schedule | sourcing_schedule_id |
| company_id | company | id |
| product_id | product | id |
| product_group_id | product_hierarchy | id |

#### Validation Rules
- **Override logic**: `product_id` > `product_group_id` > `company_id`

---

### <a name="inv_policy"></a>11. inv_policy (Inventory Policy)

**Purpose**: Determines stock management approach (safety stock policy)

#### Primary Key (Composite)
- `site_id` + `id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| site_id | string | Yes | Site identifier (FK) |
| id | string | Yes | Policy identifier |
| dest_geo_id | string | Yes | Destination geography (FK) |
| product_id | string | No | Product ID (FK) - either product_id or product_group_id required |
| product_group_id | string | No | Product group (FK) - either product_id or product_group_id required |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |
| company_id | string | No | Company ID (FK) |
| ss_policy | string | Yes | Safety stock policy: `abs_level`, `doc_dem`, `doc_fcst`, `sl` |
| target_inventory_qty | numeric | Yes | Target inventory (required when ss_policy = `abs_level`) |
| target_doc_limit | numeric | Yes | Target days of cover (required when ss_policy = `doc_dem` or `doc_fcst`) |
| target_sl | numeric | Yes | Target service level (required when ss_policy = `sl`) |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| site_id | site | id |
| product_id | product | id |
| product_group_id | product_hierarchy | id |
| dest_geo_id | geography | id |
| company_id | company | id |

#### Validation Rules
- **ss_policy values**: Must be `abs_level`, `doc_dem`, `doc_fcst`, or `sl`
- **Conditional requirements**:
  - `abs_level`: Requires `target_inventory_qty`
  - `doc_dem` or `doc_fcst`: Requires `target_doc_limit`
  - `sl`: Requires `target_sl`
- **Override logic**: `product_id` > `product_group_id` > `site_id` > `dest_geo_id` > `segment_id` > `company_id`

---

### <a name="inv_level"></a>12. inv_level (Inventory Level)

**Purpose**: Snapshot of product inventory at site (beginning inventory)

#### Primary Key (Composite)
- `snapshot_date` + `site_id` + `product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| snapshot_date | date | Yes | Inventory snapshot date |
| site_id | string | Yes | Site identifier (FK) |
| product_id | string | Yes | Product identifier (FK) |
| company_id | string | No | Company ID (FK) |
| on_hand_inventory | numeric | Yes | Available inventory quantity |
| allocated_inventory | numeric | No | Allocated/reserved inventory |
| bound_inventory | numeric | No | Bound/in-transit inventory |
| lot_number | string | Yes | Lot/batch number. Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| expiry_date | date | No | Product expiration date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| site_id | site | id |
| product_id | product | id |
| company_id | company | id |

---

### <a name="vendor_product"></a>13. vendor_product

**Purpose**: Defines products supplied by each vendor

#### Primary Key (Composite)
- `vendor_tpartner_id` + `product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| company_id | string | No | Company ID (FK) |
| vendor_tpartner_id | string | Yes | Vendor/supplier trading partner ID (FK) |
| product_id | string | Yes | Supplied product (FK) |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| vendor_tpartner_id | trading_partner | id |
| product_id | product | id |

---

### <a name="vendor_lead_time"></a>14. vendor_lead_time

**Purpose**: Defines vendor lead times (order placement to receipt)

#### Primary Key (Composite)
- `vendor_tpartner_id` + `site_id` + `product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| company_id | string | No | Company ID (FK) |
| vendor_tpartner_id | string | Yes | Vendor trading partner ID (FK) |
| product_id | string | No | Product (FK) - can be at product or group level |
| site_id | string | Yes | Receiving site (FK) |
| planned_lead_time | numeric | Yes | Lead time duration |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |
| product_group_id | string | Yes | Product group (FK). Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| region_id | string | Yes | Region (FK). Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| vendor_tpartner_id | trading_partner | id |
| product_id | product | id |
| product_group_id | product_hierarchy | id |
| site_id | site | id |
| region_id | geography | id |

#### Validation Rules
- **Override logic**: `product` > `product_group` > `site` > `region` > `product_segment` > `company`

---

### <a name="supply_planning_parameters"></a>15. supply_planning_parameters

**Purpose**: Assigns planning responsibility and parameters (optional)

#### Primary Key (Composite)
- `product_id` + `eff_start_date`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| product_id | string | Yes | Product identifier (FK) |
| product_group_id | string | Yes | Product group (FK). For future use: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| site_id | string | Yes | Site (FK). For future use: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| planner_name | string | No | Assigned planner |
| demand_time_fence_days | numeric | No | Demand time fence (future use) |
| forecast_consumption_backward_days | numeric | No | Forecast consumption lookback (future use) |
| forecast_consumption_forward_days | numeric | No | Forecast consumption lookahead (future use) |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| product_id | product | id |
| product_group_id | product_hierarchy | id |
| site_id | site | id |

---

## Manufacturing Entities

### <a name="product_bom"></a>16. product_bom (Bill of Materials)

**Purpose**: Defines component requirements for manufacturing

#### Primary Key (Composite)
- `id` + `product_id` + `component_product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes (Mfg) / No (AR) | BOM identifier |
| product_id | string | Yes (Mfg) / No (AR) | Finished product (FK) |
| component_product_id | string | Yes (Mfg) / No (AR) | Component product (FK) |
| component_quantity_per | double | Yes (Mfg) / No (AR) | Quantity per unit of finished product |
| site_id | string | Yes (Mfg) / No (AR) | Manufacturing site (FK) |
| production_process_id | string | Yes (Mfg) / No (AR) | Production process (FK) |
| company_id | string | No | Company ID (FK) |
| level | int | No | BOM level in multi-level BOM |
| component_quantity_uom | string | No | Component unit of measure |
| component_line_number | int | No | Child record line ID |
| lifecycle_phase | string | No | Life cycle phase |
| assembly_cost | double | No | Assembly cost |
| assembly_cost_uom | string | No | Assembly cost UOM |
| eff_start_date | timestamp | Yes (Mfg) / No (AR) | Effective start date |
| eff_end_date | timestamp | Yes (Mfg) / No (AR) | Effective end date |
| description | string | No | BOM description |
| alternative_product_id | string | No | Alternate product (FK) |
| priority | string | No | Component priority |
| alternate_group_id | string | No | Alternate product group ID |
| alternate_product_qty | double | No | Alternate product quantity |
| alternate_product_qty_uom | string | No | Alternate product UOM |
| ratio | double | No | Product ratio in BOM |
| creation_date | timestamp | No | BOM creation date |
| change_date | timestamp | No | BOM update date |
| source | string | No | Data source |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| component_product_id | product | id |
| site_id | site | id |
| production_process_id | production_process | production_process_id |
| alternative_product_id | product_alternate | product_alternate_id |

#### Validation Rules
- **Manufacturing Plan**: All marked fields are required
- **Auto Replenishment (AR)**: Most fields are not required

---

### <a name="production_process"></a>17. production_process

**Purpose**: Defines manufacturing/assembly processes with lead times (Manufacturing Plan only)

#### Primary Key
- `production_process_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| production_process_id | string | Yes (Mfg) / No (AR) | Process identifier |
| production_process_name | string | No | Process name |
| product_id | string | Yes (Mfg) / No (AR) | Product produced (FK) |
| site_id | string | Yes (Mfg) / No (AR) | Production site (FK) |
| company_id | string | No | Company ID (FK) |
| setup_time | numeric | No | Setup time required |
| setup_time_uom | string | No | Setup time unit (e.g., minutes, hours) |
| operation_time | numeric | No | Operation/cycle time |
| operation_time_uom | string | No | Operation time unit |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| product_id | product | id |
| site_id | site | id |
| company_id | company | id |

---

## Inbound Order Entities

### <a name="inbound_order"></a>18. inbound_order

**Purpose**: Inbound order header (POs, transfer orders, manufacturing orders)

#### Primary Key (Composite)
- `id` + `tpartner_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Object ID |
| tpartner_id | string | Yes | Trading partner sending order (FK) |
| company_id | string | No | Company ID (FK) |
| order_creation_date | timestamp | No | Order creation date |
| order_type | string | No | Order type: PO, TO, MO, BO, CO |
| order_status | string | No | Order status |
| to_site_id | string | No | Site where order arrives (FK) |
| order_currency_uom | string | No | Company currency UOM |
| vendor_currency_uom | string | No | Vendor currency UOM |
| exchange_rate | double | No | Currency exchange rate |
| exchange_rate_date | timestamp | No | Exchange rate calculation date |
| incoterm | string | No | Three-letter incoterm code |
| incoterm2 | string | No | Place of ownership transfer |
| incoterm_location_1 | string | No | Incoterm location 1 |
| incoterm_location_2 | string | No | Incoterm location 2 |
| submitted_date | timestamp | No | Order submission date/time |
| agreement_start_date | timestamp | No | Contract start date/time |
| agreement_end_date | timestamp | No | Contract end date/time |
| shipping_instr_code | string | No | Shipping instructions code |
| payment_terms_code | string | No | Payment instructions code |
| std_terms_agreement | string | No | Agreement between company and vendor |
| std_terms_agreement_ver | string | No | Agreement version |
| agreement_number | string | No | Contract/agreement number |
| inbound_order_url | string | No | URL to source system record |
| source_update_dttm | timestamp | No | Source system update timestamp |
| source_event_id | string | No | Source system event ID |
| source | string | No | Data source |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| tpartner_id | trading_partner | id |
| company_id | company | id |
| to_site_id | site | id |

#### Validation Rules
- **Order types**: PO (Purchase), TO (Transfer), MO (Manufacturing), BO (Blanket), CO (Consumption)

---

### <a name="inbound_order_line"></a>19. inbound_order_line

**Purpose**: Line-level data for inbound orders

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Order line identifier |
| order_id | string | Yes | Parent order ID (FK) |
| order_type | string | Yes | Order type |
| status | string | No | Line status |
| product_id | string | Yes | Product being ordered (FK) |
| to_site_id | string | Yes | Receiving site (FK) |
| from_site_id | string | No | Shipping site (FK) |
| quantity_submitted | numeric | Yes | Submitted quantity (at least one quantity field required) |
| quantity_confirmed | numeric | No | Confirmed quantity |
| quantity_received | numeric | No | Received quantity |
| expected_delivery_date | date | Yes | Expected delivery date |
| submitted_date | date | No | Submission date |
| incoterm | string | No | Incoterms code |
| company_id | string | No | Company ID (FK) |
| tpartner_id | string | Yes | Trading partner ID (FK) |
| quantity_uom | string | No | Quantity unit of measure |
| reservation_id | string | No | Associated reservation |
| reference_object_type | string | No | Links PO requests to POs for tracking |
| reference_object_id | string | No | Reference object ID for PO tracking |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| order_id | inbound_order | id |
| product_id | product | id |
| to_site_id | site | id |
| from_site_id | site | id |
| tpartner_id | trading_partner | id |
| company_id | company | id |

#### Validation Rules
- **At least one quantity field required**: `quantity_submitted`, `quantity_confirmed`, or `quantity_received`

---

### <a name="inbound_order_line_schedule"></a>20. inbound_order_line_schedule

**Purpose**: Schedule-line level data within inbound orders

#### Primary Key (Composite)
- `id` + `order_id` + `order_line_id` + `product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Schedule line ID (must be unique) |
| order_id | string | Yes | Parent order ID (FK) |
| order_line_id | string | Yes | Parent order line ID (FK) |
| product_id | string | Yes | Product ID (FK) |
| company_id | string | No | Company ID (FK) |
| status | string | No | Line status: Cancelled, Open, Closed, InTransit, Confirmed, null, or custom |
| schedule_creation_date | timestamp | No | Schedule creation date |
| external_line_number | string | No | External line number |
| expected_delivery_date | timestamp | No | Expected delivery date |
| confirmation_date | timestamp | No | Vendor confirmation date/time |
| goods_issue_date | timestamp | No | Material availability date at origin |
| material_availability_date | timestamp | No | Material availability date at origin |
| ship_date | timestamp | No | Vendor ship date/time |
| delivery_date | timestamp | No | Vendor delivery date/time |
| quantity_submitted | double | No | Submitted quantity |
| quantity_confirmed | double | No | Confirmed quantity |
| quantity_received | double | No | Received quantity |
| sap_lips__vbeln | string | No | SAP Delivery Number (predicate key) |
| sap_vttp__tknum | string | No | SAP Shipment Number (predicate key) |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| order_id | inbound_order | id |
| order_line_id | inbound_order_line | id |

#### Validation Rules
- **Status values**: Reserved values (Cancelled, Open, Closed, InTransit, Confirmed) or custom/null accepted

---

## Shipment Entities

### <a name="shipment"></a>21. shipment

**Purpose**: Inbound shipment information (origin, carrier, dates, quantities)

#### Primary Key (Composite)
- `id` + `supplier_tpartner_id` + `product_id` + `order_id` + `order_line_id` + `package_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Shipment identifier |
| supplier_tpartner_id | string | Yes | Supplier partner ID (FK) |
| product_id | string | Yes | Product ID (FK) |
| order_id | string | Yes | Order ID (FK) |
| order_line_id | string | Yes | Order line ID (FK) |
| package_id | string | Yes | Package ID |
| creation_date | timestamp | No | Creation date |
| packaging_hierarchy_type | string | No | Shipment structure: container, pallet, carton |
| supplier_description | string | No | Partner description |
| company_id | string | No | Company ID (FK) |
| customer_description | string | No | Customer description |
| ship_from_site_id | string | No | Origin site (FK) |
| ship_from_site_description | string | No | Origin site description |
| ship_from_site_address_1 | string | No | Origin address line 1 |
| ship_from_site_address_2 | string | No | Origin address line 2 |
| ship_from_site_address_city | string | No | Origin city |
| ship_from_site_address_state | string | No | Origin state |
| ship_from_site_address_country | string | No | Origin country |
| ship_from_site_address_zip | string | No | Origin postal code |
| ship_to_site_id | string | No | Destination site (FK) |
| ship_to_site_description | string | No | Destination site description |
| ship_to_site_address_1 | string | No | Destination address line 1 |
| ship_to_site_address_2 | string | No | Destination address line 2 |
| ship_to_site_address_city | string | No | Destination city |
| ship_to_site_address_state | string | No | Destination state |
| ship_to_site_address_country | string | No | Destination country |
| ship_to_site_address_zip | string | No | Destination postal code |
| ship_to_site | string | No | Final ship to location (FK) |
| origin_port | string | No | Port of loading |
| destination_port | string | No | Port of destination |
| transportation_mode | string | No | Mode of transport |
| routing_sequence | string | No | Routing sequence ID from ASN |
| routing_description | string | No | Routing description |
| carrier_id | string | No | Carrier ID |
| carrier_description | string | No | Carrier description |
| service_level | string | No | Service level |
| transportation_id | string | No | Vessel code or trailer number |
| transportation_description | string | No | Vessel description |
| conveyance_id | string | No | Trip number |
| bill_of_lading_number | string | No | BOL number |
| master_bill_of_lading_number | string | No | Master BOL number |
| carrier_reference_number | string | No | Carrier reference |
| shipper_reference_number | string | No | Shipper reference |
| equipment_code | string | No | Equipment code |
| equipment_number | string | No | Equipment number |
| seal_number | string | No | Seal number |
| equipment_type | string | No | Type of equipment |
| package_type | string | No | Type of package |
| package_quantity | double | No | Quantity of packages |
| weight_qualifier | string | No | Weight type (e.g., consolidated weight) |
| weight | double | No | Product weight |
| weight_uom | string | No | Weight unit of measure |
| volume | double | No | Volume of shipment |
| volume_uom | string | No | Volume unit of measure |
| product_description | string | No | Product description |
| tp_product_id | string | No | Trading partner product ID |
| upc | string | No | UPC code |
| hts_code | string | No | Harmonized Tariff Schedule code |
| units_shipped | double | No | Units shipped |
| units_received | double | No | Received quantity at shipment level |
| uom | string | No | Unit of measurement |
| order_type | string | No | Order type |
| order_customer_tpartner_id | string | No | Customer ID of order |
| order_supplier_tpartner_id | string | No | Supplier ID of order |
| shipment_status | string | No | Shipment status |
| planned_ship_date | timestamp | No | Planned shipping date |
| actual_ship_date | timestamp | No | Actual shipping date |
| planned_delivery_date | timestamp | No | Planned delivery date |
| actual_delivery_date | timestamp | No | Actual delivery date |
| carrier_eta_date | timestamp | No | ETA from carrier |
| latest_milestone | string | No | Milestone event/status description |
| latest_milestone_date | timestamp | No | Latest milestone date |
| incoterms | string | No | Three-letter incoterm code |
| line_id | string | No | Shipment line ID |
| source_update_dttm | timestamp | No | Source system update timestamp |
| source_event_id | string | No | Source system event ID |
| source | string | No | Data source |
| sap_vttp__vbeln | string | No | SAP Delivery Number |
| sap_but021_fs__addrnumber | string | No | SAP Address Number (Ship-to) |
| sap_t001w__adrnr | string | No | SAP Address Number |
| sap_vttk__bev1_rpmowa | string | No | SAP Vehicle number |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| supplier_tpartner_id | trading_partner | id |
| company_id | company | id |
| ship_from_site_id | site | id |
| ship_to_site_id | site | id |
| ship_to_site | site | id |
| product_id | product | id |
| order_id | inbound_order | id |
| order_line_id | inbound_order_line | id |

#### Validation Rules
- **Date fields**: Use one of: `planned_delivery_date`, `actual_delivery_date`, or `carrier_eta_date`
- **Ship date**: Use one of: `planned_ship_date` or `actual_ship_date`

---

### <a name="shipment_stop"></a>22. shipment_stop

**Purpose**: Multiple stops for shipments (pickup/delivery locations with dates/times)

#### Primary Key (Composite)
- `shipment_stop_id` + `shipment_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| shipment_stop_id | string | Yes | Shipment stop ID |
| shipment_id | string | Yes | Shipment ID (FK) |
| sequence | int | No | Sequence of the shipment |
| company_id | string | No | Company ID (FK) |
| site_id | string | No | Site ID (FK) |
| planned_arrival_start_dttm | timestamp | No | Planned arrival start date/time |
| planned_arrival_end_dttm | timestamp | No | Planned arrival end date/time |
| planned_departure_start_dttm | timestamp | No | Planned departure start date/time |
| planned_departure_end_dttm | timestamp | No | Planned departure end date/time |
| actual_arrival_start_dttm | timestamp | No | Actual arrival start date/time |
| actual_arrival_end_dttm | timestamp | No | Actual arrival end date/time |
| actual_departure_start_dttm | timestamp | No | Actual departure start date/time |
| actual_departure_end_dttm | timestamp | No | Actual departure end date/time |
| appointment_number | string | No | Appointment number |
| delivery_number | string | No | Delivery number |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| site_id | site | id |
| shipment_id | shipment | id |

---

### <a name="shipment_lot"></a>23. shipment_lot (Supply Planning Only)

**Purpose**: Shipment details per lot (lot tracking and expiration)

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Shipment lot identifier |
| lot_qty | numeric | Yes | Quantity in lot |
| expiry_date | date | No | Lot expiration date |
| shipment_id | string | Yes | Parent shipment (FK) |
| product_id | string | Yes | Product (FK). Default: `SCN_RESERVED_NO_VALUE_PROVIDED` |
| tpartner_id | string | No | Trading partner |
| order_id | string | No | Order identifier |
| order_line_id | string | No | Order line identifier |
| package_id | string | No | Package identifier |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| shipment_id | shipment | id |
| product_id | product | id |

---

## Outbound Fulfillment Entities

### <a name="outbound_order_line"></a>24. outbound_order_line

**Purpose**: Customer orders and demand history

#### Primary Key (Composite)
- `id` + `cust_order_id` + `product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Outbound order line ID |
| cust_order_id | string | Yes | Outbound order ID |
| product_id | string | Yes | Product ID (FK) |
| company_id | string | No | Company ID (FK) |
| order_date | timestamp | No | Order placement date/time |
| product_group_id | string | No | Product group ID (FK) |
| customer_tpartner_id | string | No | Customer trading partner ID (FK) |
| status | string | No | Customer order status |
| init_quantity_requested | double | No | Original order quantity |
| final_quantity_requested | double | No | Final quantity after changes |
| quantity_uom | string | No | Quantity unit of measure |
| requested_delivery_date | timestamp | No | Requested delivery date |
| promised_delivery_date | timestamp | No | Promised delivery date |
| actual_delivery_date | timestamp | No | Actual delivery date |
| list_price | double | No | List price |
| sold_price | double | No | Selling price after discounts |
| discount | double | No | Discount applied |
| discount_code | string | No | Discount code used |
| currency_uom | string | No | Currency unit of measure |
| tax | double | No | Tax amount |
| incoterm1 | string | No | Place of ownership transfer |
| incoterm2 | string | No | Place of ownership transfer |
| ship_from_site_id | string | No | Origin site (FK) |
| ship_to_site_id | string | No | Destination site (FK) |
| ship_to_site_address_1 | string | No | Destination address line 1 |
| ship_to_site_address_2 | string | No | Destination address line 2 |
| ship_to_site_address_city | string | No | Destination city |
| ship_to_site_address_state | string | No | Destination state |
| ship_to_site_address_country | string | No | Destination country |
| ship_to_site_address_zip | string | No | Destination postal code |
| availability_status | string | No | In-stock availability at order time |
| quantity_promised | double | No | Promised quantity |
| quantity_delivered | double | No | Delivered quantity |
| channel_id | string | No | Channel used to place order |
| sap_2lis_11_vahdr__vbeln | string | No | SAP reference document number |
| sap_2lis_11_vaitm__kunnr | string | No | SAP sold to party |
| sap_2lis_11_vaitm__vkorg | string | No | SAP sales organization |
| sap_2lis_11_vaitm__vtweg | string | No | SAP distribution channel |
| sap_2lis_11_vaitm__spart | string | No | SAP division |
| sap_2lis_11_vaitm__pkunre | string | No | SAP bill-to party |
| source | string | No | Data source |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| product_group_id | product_hierarchy | id |
| customer_tpartner_id | trading_partner | id |
| ship_from_site_id | site | id |
| ship_to_site_id | site | id |

#### Usage Notes
- **Demand History**: Supply Planning calculates historical average demand from past 30 days using:
  - `actual_delivery_date` (or `promised_delivery_date` if missing)
  - `quantity_delivered` (or `quantity_promised` or `final_quantity_requested` if missing)

---

### <a name="outbound_shipment"></a>25. outbound_shipment

**Purpose**: Outbound shipment information to customers

#### Primary Key (Composite)
- `id` + `cust_order_id` + `cust_order_line_id` + `product_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| id | string | Yes | Outbound shipment ID |
| cust_order_id | string | Yes | Customer order ID (FK) |
| cust_order_line_id | string | Yes | Customer order line ID (FK) |
| product_id | string | Yes | Product ID (FK) |
| company_id | string | No | Company ID (FK) |
| shipped_qty | double | No | Shipment quantity |
| cust_shipment_status | string | No | Status: canceled, open, closed, delivered |
| expected_ship_date | timestamp | No | Expected ship date from company location |
| actual_ship_date | timestamp | No | Actual ship date from company location |
| from_site_id | string | No | Origin site (FK) |
| to_site_id | string | No | Destination site (FK) |
| expected_delivery_date | timestamp | No | Expected delivery date to customer |
| actual_delivery_date | timestamp | No | Actual delivery date to customer |
| shipping_cost | double | No | Final shipping cost |
| tracking_number | string | No | Shipment tracking number |
| bill_weight | double | No | Shipped weight for billing |
| sap_2lis_08trtlp__vbeln | string | No | SAP delivery number (predicate key) |
| sap_2lis_08trtlp__posnr | string | No | SAP delivery item number (predicate key) |
| sap_2lis_08trtlp__tknum | string | No | SAP shipment item number (predicate key) |
| source | string | No | Data source |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |
| tpartner_id | string | No | Trading partner ID (FK) |
| service_level | string | No | Service level: Standard, next day, two-day, expedited |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| cust_order_id | outbound_order_line | cust_order_id |
| cust_order_line_id | outbound_order_line | id |
| from_site_id | site | id |
| to_site_id | site | id |
| tpartner_id | trading_partner | id |

---

## Planning Output Entities

### <a name="supply_plan"></a>26. supply_plan

**Purpose**: Supply plan generated by AWS Supply Chain Supply Planning

#### Primary Key
- `supply_plan_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| supply_plan_id | string | Yes | Supply plan ID |
| company_id | string | No | Company ID (FK) |
| plan_uuid | string | No | Unique plan identifier generated by application |
| snapshot_date | timestamp | No | Date/time till when data is collected |
| creation_date | timestamp | No | Plan creation date/time |
| status | string | No | Supply plan status |
| tpartner_id | string | No | Trading partner ID (FK) |
| product_id | string | No | Product ID (FK) |
| product_group_id | string | No | Product group ID (FK) |
| to_site_id | string | No | Site where order will arrive (FK) |
| from_site_id | string | No | Site where order originates (FK) |
| plan_need_by_date | timestamp | No | Future date when supply is needed at to_site_id |
| plan_quantity | double | No | Planned quantity |
| commit_date | timestamp | No | Date committed by trading partner |
| commit_quantity | double | No | Quantity committed by trading partner |
| supply_upside | double | No | Upside capacity published by supplier |
| plan_type | string | No | Type of plan (e.g., Forecast Commit, Supplier Plan) |
| plan_window_start | timestamp | No | Start of planning window/bucket |
| plan_window_end | timestamp | No | End of planning window/bucket |
| source | string | No | Source of data |
| production_process_id | string | No | Production process ID (FK) |
| plan_cycle_sequence | double | No | Sequence number of plan cycle |
| quantity_uom | string | No | Unit of Measure for quantity |
| plan_id | string | No | Recurring plan ID covering multiple records |
| plan_sequence_id | string | No | Unique identifier/sequence for each plan version |
| plan_cost | double | No | Estimated/projected cost (materials, labor, transport, storage) |
| required_date | timestamp | No | Date to execute plan under specific supply_plan |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |
| total_supply_quantity | double | No | Total supply expected on plan_need_by_date |
| projected_inventory_level | double | No | Inventory quantity projected on plan_need_by_date |
| target_inventory_level | double | No | Target inventory level on required_date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| product_group_id | product_hierarchy | id |
| tpartner_id | trading_partner | id |
| to_site_id | site | id |
| from_site_id | site | id |
| production_process_id | production_process | production_process_id |

---

### <a name="reservation"></a>27. reservation

**Purpose**: Inventory reservation details

#### Primary Key (Composite)
- `reservation_id` + `reservation_detail_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| reservation_id | string | Yes | Reservation ID |
| reservation_detail_id | string | Yes | Reservation detail ID |
| reservation_type | string | No | Type: procurement, build-to-stock, etc. |
| company_id | string | No | Company ID (FK) |
| status | string | No | Reservation status |
| product_id | string | No | Product ID (FK) |
| site_id | string | No | Site ID (FK) |
| quantity | double | No | Reservation quantity |
| quantity_uom | string | No | Quantity UOM |
| reservation_date | timestamp | No | Reservation generation date |
| is_deleted | string | No | Yes/No deletion status indicator |
| requisition_id | string | No | Source reference to inbound order (FK) |
| requisition_line_id | string | No | Source reference to inbound order line (FK) |
| rfq_id | string | No | Source reference to RFQ order (FK) |
| rfq_line_id | string | No | Source reference to RFQ order line (FK) |
| order_id | string | No | Source reference to inbound order (FK) |
| order_line_id | string | No | Source reference to inbound order line (FK) |
| order_line_schedule_id | string | No | Source reference to schedule (FK) |
| stock_transfer_1_order_id | string | No | Stock transfer order ID |
| stock_transfer_1_order_line_id | string | No | Stock transfer order line ID |
| stock_transfer_2_order_id | string | No | Stock transfer order ID |
| stock_transfer_2_order_line_id | string | No | Stock transfer order line ID |
| source_update_dttm | timestamp | No | Source system update timestamp |
| source_event_id | string | No | Source system event ID |
| source | string | No | Data source identifier |
| flex_1 | string | No | Flexible custom field 1 |
| flex_2 | string | No | Flexible custom field 2 |
| flex_3 | string | No | Flexible custom field 3 |
| flex_4 | string | No | Flexible custom field 4 |
| flex_5 | string | No | Flexible custom field 5 |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| site_id | site | id |
| company_id | company | id |
| product_id | product | id |
| requisition_id, rfq_id | inbound_order_line | order_id |
| requisition_line_id, rfq_line_id | inbound_order_line | id |
| order_line_schedule_id | inbound_order_line_schedule | id |

---

## Forecast Entities

### <a name="forecast"></a>28. forecast

**Purpose**: Demand forecast data (deterministic or stochastic)

#### Primary Key (Composite)
- `snapshot_date` + `product_id` + `site_id` + `region_id` + `product_group_id` + `forecast_start_dttm` + `forecast_end_dttm`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| snapshot_date | timestamp | Yes | Date up to when data was captured |
| product_id | string | Yes | Product or product group level (FK) |
| site_id | string | Yes | Site for which forecast is generated (FK) |
| region_id | string | Yes | Geographical region ID (FK) |
| product_group_id | string | Yes | Product group ID (FK) |
| forecast_start_dttm | timestamp | Yes | Forecast start date/time |
| forecast_end_dttm | timestamp | Yes | Forecast end date/time |
| creation_date | timestamp | No | Forecast creation date |
| company_id | string | No | Company ID (FK) |
| source | string | No | Data source |
| mean | double | No | Mean value of forecast |
| p10 | double | No | 10th percentile (required for `sl` policy) |
| p20 | double | No | 20th percentile |
| p30 | double | No | 30th percentile |
| p40 | double | No | 40th percentile |
| p50 | double | No | 50th percentile / median (required for `sl` and `doc_fcst` policies) |
| p60 | double | No | 60th percentile |
| p70 | double | No | 70th percentile |
| p80 | double | No | 80th percentile |
| p90 | double | No | 90th percentile (required for `sl` policy) |
| default_price | double | No | Default MSRP |
| forecast_price | double | No | Price at which product was forecast to be sold |
| num_causals | int | No | Number of causals applied |
| causal_start | timestamp | No | Causal start date |
| causal_end | timestamp | No | Causal end date |
| user_override | double | No | User override of forecast quantity |
| user_id | string | No | ID of user who overrode forecast |
| act_qty | double | No | Actual order quantity sold in period |
| channel_id | string | No | Unique channel identifier |
| tpartner_id | string | No | Trading partner ID (FK) |
| user_override_p10 | double | No | User override for P10 |
| user_override_p20 | double | No | User override for P20 |
| user_override_p30 | double | No | User override for P30 |
| user_override_p40 | double | No | User override for P40 |
| user_override_p50 | double | No | User override for P50 |
| user_override_p60 | double | No | User override for P60 |
| user_override_p70 | double | No | User override for P70 |
| user_override_p80 | double | No | User override for P80 |
| user_override_p90 | double | No | User override for P90 |
| postal_code | string | No | Trading partner's postal code |
| tpartner_type | string | No | Trading partner type |
| quantity_uom | string | No | Quantity unit of measure |
| demand_plan_id | string | No | Demand plan ID |
| plan_sequence_id | string | No | Unique identifier/sequence for each plan version |
| plan_type | string | No | Type of forecast or plan |
| plan_window_start | timestamp | No | Planning window/bucket start |
| plan_window_end | timestamp | No | Planning window/bucket end |
| ship_to_site_id | string | No | Site to which order is shipped (FK) |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |
| status | string | No | Plan status: created, saved, published |
| plan_name | string | No | Demand plan name |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| product_id | product | id |
| region_id | geography | id |
| product_group_id | product_hierarchy | id |
| site_id | site | id |
| tpartner_id | trading_partner | id |
| ship_to_site_id | outbound_order_line | ship_to_site_id |

#### Validation Rules
- **Forecast Types**:
  - **Deterministic**: Only `mean` populated
  - **Stochastic**: P10/P50/P90 ± mean
- **Policy Requirements**:
  - `sl` policy: Requires P10, P50, P90
  - `doc_fcst` policy: Requires P50 or mean
- **Quantile Ordering**: P10 ≤ P20 ≤ P30 ≤ P40 ≤ P50 ≤ P60 ≤ P70 ≤ P80 ≤ P90
- **Temporal Constraints**:
  - `forecast_start_dttm` ≤ `forecast_end_dttm`
  - `causal_start` ≤ `causal_end`
  - `plan_window_start` ≤ `plan_window_end`

---

### <a name="supplementary_time_series"></a>29. supplementary_time_series

**Purpose**: Additional demand drivers (price, promotions, out-of-stock)

#### Primary Key
- `id` (string)

#### Fields

| Column | Data Type | Required | Description | Constraints |
|--------|-----------|----------|-------------|-------------|
| id | string | Yes | Unique identifier |  |
| product_id | string | No | Product identifier (FK) |  |
| product_group_id | string | No | Product group |  |
| order_date | timestamp | Yes | Timestamp for time-series data |  |
| channel_id | string | No | Channel identifier |  |
| customer_tpartner_id | string | No | Customer/trading partner (FK) |  |
| site_id | string | No | Site identifier (FK) |  |
| ship_to_site_id | string | No | Destination site (FK) |  |
| ship_to_site_address_zip | string | No | Destination postal code |  |
| geo_id | string | No | Geographical hierarchy ID (FK) |  |
| ship_from_site_id | string | No | Origin site (FK) |  |
| ship_from_site_address_zip | string | No | Origin postal code |  |
| time_series_name | string | Yes | Name identifier for time series | Must start with letter; 2-56 chars; letters, numbers, underscores only |
| time_series_value | string | Yes | Value for time series | Numerical values only for demand planning |
| source_event_id | string | No | Source system event ID |  |
| source_update_dttm | timestamp | No | Source system update timestamp |  |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| product_id | product | id |
| site_id | site | id |
| customer_tpartner_id | trading_partner | id |
| ship_to_site_id | outbound_order_line | ship_to_site_id |
| geo_id | geography | id |
| ship_from_site_id | outbound_order_line | ship_from_site_id |

#### Validation Rules
- **time_series_name**:
  - Must start with a letter
  - 2-56 characters
  - Only letters, numbers, and underscores (no special characters)
- **time_series_value**: Numerical values only for demand planning
- **Usage**: Optional but recommended; supports up to 13 demand drivers

---

## Operations Entities

### <a name="process_header"></a>30. process_header

**Purpose**: Track execution activities (manufacturing, maintenance, repairs) at plant/site level

#### Primary Key
- `process_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| process_id | string | Yes | Process ID (order, work order, maintenance order) |
| ... | ... | ... | (Full schema not available in search results) |

#### Notes
- **Relationships**: One-to-one with `process_product` (work order line)
- Full field details require direct AWS documentation access

---

### <a name="process_operation"></a>31. process_operation

**Purpose**: Operation definitions associated with activities (e.g., Stop machine, Oiling)

#### Primary Key (Composite)
- `process_operation_id` + `process_id`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| process_operation_id | string | Yes | Type of process operation |
| process_id | string | Yes | Process ID (FK) |
| company_id | string | No | Company ID (FK) |
| type | string | No | Type of operation (e.g., open machine) |
| site_location | string | No | Location or section in site/plant |
| status | string | No | Process status |
| operation_name | string | No | Operation name |
| operation_sequence | string | No | Sequence of operation within process |
| planned_start_dttm | timestamp | No | Planned start date-time |
| planned_end_dttm | timestamp | No | Planned end date-time |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| process_id | process_header | process_id |
| company_id | company | id |

---

### <a name="process_product"></a>32. process_product

**Purpose**: Product/material associated with activities (work order line)

#### Primary Key
- (Not specified in available documentation)

#### Fields
- **Relationships**: One-to-one with `process_header` and `process_operation`
- Full field details require direct AWS documentation access

---

### <a name="work_order_plan"></a>33. work_order_plan

**Purpose**: Supply chain process plan for work orders (source type, duration)

#### Primary Key (Composite)
- `process_id` + `product_id` + `business_process_id` + `business_process_sequence`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| process_id | string | Yes | Process ID (FK) |
| product_id | string | Yes | Product ID (material) in work order |
| business_process_id | string | Yes | Business process: PO, PR, RFQ, etc. |
| business_process_sequence | int | Yes | Business process sequence number |
| duration | int | Yes | Unit in days |
| process_product_id | string | No | ID associated with process and product |
| preferred_source | string | No | Source type: inventory or direct purchase |
| site_id | string | No | Site linked to business process |
| notes | string | No | Additional notes |
| flex_1 | string | No | Flexible field 1 |
| flex_2 | string | No | Flexible field 2 |
| flex_3 | string | No | Flexible field 3 |
| flex_4 | string | No | Flexible field 4 |
| flex_5 | string | No | Flexible field 5 |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| process_id | process_header | id |

#### Validation Rules
- **site_id**: Optional for purchasing processes; mandatory for distribution
- **Coverage**: Plan must include both purchasing AND distribution processes

---

## Cost Management Entities

### <a name="customer_cost"></a>34. customer_cost

**Purpose**: Costs incurred during supply chain operations

#### Primary Key (Composite)
- `cost_id` + `incurred_date`

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| cost_id | string | Yes | Unique cost record identifier |
| customer_id | string | Yes | User incurring cost (FK) |
| incurred_date | timestamp | Yes | Date/time when cost was incurred |
| order_id | string | No | User order associated with cost (FK) |
| shipment_id | string | No | Outbound shipment (FK) |
| cost_type | string | No | Cost type: handling, packing, storage, shipping |
| amount | double | No | Cost amount |
| amount_uom | string | No | Amount unit of measure |
| tax_1 | string | No | Tax amount |
| tax_2 | string | No | Additional tax |
| tax_3 | string | No | Additional tax |
| tax_uom | string | No | Tax unit of measure |
| currency_uom | string | No | Currency unit of measure |
| payment_status | string | No | Payment status: Pending, Paid |
| incoterm | string | No | Trade terms: FOB, ExWorks, DDP |
| source | string | No | Data source |
| source_event_id | string | No | Source system event ID |
| source_update_dttm | timestamp | No | Source system update timestamp |
| discount_1 | double | No | Discount |
| discount_2 | double | No | Additional discount |
| discount_3 | double | No | Additional discount |
| online_order_id | string | No | Unique order line identifier |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| customer_id | trading_partner | id |
| order_id | outbound_order_line | id |
| shipment_id | outbound_shipment | id |

---

## Segmentation Entities

### <a name="segmentation"></a>35. segmentation

**Purpose**: Product/site segmentation for planning

#### Primary Key
- `segment_id` (string)

#### Fields

| Column | Data Type | Required | Description |
|--------|-----------|----------|-------------|
| segment_id | string | Yes | Segment identifier |
| creation_date | date | Yes | Segment creation date |
| company_id | string | No | Company ID (FK) |
| site_id | string | Yes | Associated site (FK) |
| product_id | string | Yes | Associated product (FK) |
| segment_description | string | No | Segment description |
| segment_type | string | No | Type of segment |
| segment_value | string | No | Segment value/classification |
| source | string | No | Segment source |
| eff_start_date | date | Yes | Effective start date |
| eff_end_date | date | Yes | Effective end date |

#### Foreign Keys
| Column | References | Target Column |
|--------|-----------|---------------|
| company_id | company | id |
| site_id | site | id |
| product_id | product | id |

---

## Entity Relationship Summary

### Core Master Data Flow
```
company
  ├── geography (parent_geo_id → geography.id)
  ├── site (geo_id → geography.id)
  ├── trading_partner (geo_id → geography.id)
  ├── product_hierarchy (parent_product_group_id → product_hierarchy.id)
  └── product (product_group_id → product_hierarchy.id)
```

### Supply Planning Flow
```
site + product
  ├── inv_level (snapshot)
  ├── inv_policy (safety stock targets)
  ├── sourcing_rules (network topology)
  │     ├── transportation_lane (for transfer)
  │     ├── vendor_product + vendor_lead_time (for buy)
  │     └── production_process + product_bom (for manufacture)
  ├── forecast (demand input)
  └── supply_plan (output)
```

### Order-to-Cash Flow
```
outbound_order_line (customer order)
  └── outbound_shipment (delivery)
```

### Procure-to-Pay Flow
```
inbound_order (PO/TO/MO header)
  ├── inbound_order_line (line items)
  │     └── inbound_order_line_schedule (schedule lines)
  └── shipment (inbound shipment)
        ├── shipment_stop (pickup/delivery stops)
        └── shipment_lot (lot tracking)
```

### Manufacturing Flow
```
product (finished good)
  └── product_bom (components)
        ├── component_product_id → product.id
        └── production_process_id → production_process.production_process_id
```

### Work Order Flow
```
process_header (work order)
  ├── process_operation (operations)
  ├── process_product (materials)
  └── work_order_plan (planning)
```

---

## Override Logic Summary

Multiple entities support hierarchical override logic for flexibility:

### sourcing_rules
```
product_id > product_group_id > company_id
```

### inv_policy
```
product_id > product_group_id > site_id > dest_geo_id > segment_id > company_id
```

### vendor_lead_time
```
product > product_group > site > region > product_segment > company
```

### sourcing_schedule_details
```
product_id > product_group_id > company_id
```

---

## Planning Process Details

### Auto Replenishment
**Required Inputs:**
1. **Forecast**: External, Demand Planning, or sales history (outbound_order_line)
2. **Inventory Level**: inv_level (beginning inventory)
3. **In-flight Orders**: inbound_order_line (open orders within horizon)
4. **Sourcing Rules**: Transfer or Buy rules
5. **Inventory Policy**: Safety stock targets (abs_level, doc_dem, doc_fcst, sl)

**Outputs:**
- supply_plan (purchase/transfer recommendations)
- reservation (allocations)

### Manufacturing Plan
**Required Inputs (all Auto Replenishment inputs PLUS):**
1. **Bill of Materials**: product_bom (component requirements)
2. **Production Process**: production_process (lead times, setup times)
3. **Sourcing Rules**: Manufacture rules with production_process_id

**Outputs:**
- supply_plan (production, transfer, and purchase recommendations)
- reservation (material allocations)

---

## Data Quality & Validation

### Required Field Validation
- Entities marked **Yes (Mfg)** vs **No (AR)**: Different requirements for Manufacturing Plan vs Auto Replenishment
- String fields with default: `SCN_RESERVED_NO_VALUE_PROVIDED` for SAP/EDI ingestion
- Timestamp defaults: `1900-01-01 00:00:00` (start) and `9999-12-31 23:59:59` (end)

### Referential Integrity
- All FK columns must reference valid records in target entities
- Planning will fail if required master data (site, product, sourcing_rules) is missing

### Planning Inclusion/Exclusion Flags
- **site.is_active**: `False` = exclude; blank/null = include
- **product.is_deleted**: `True` = exclude; `False` = include; blank/null = exclude (default)
- **trading_partner.is_active**: Controls partner availability

---

## API Integration

### SendDataIntegrationEvent
**Event Types (scn.data.*)**:
- processheader, processproduct, processoperation
- shipment, shipmentstop, shipmentstoporder, shipmentlot
- inboundorder, inboundorderline, inboundorderlineschedule
- outboundorderline, outboundshipment
- forecast, supplementarytimeseries
- invlevel, reservation
- productbom, productionprocess
- And all other entities...

**Requirements:**
- Data payload must follow entity schema
- Timestamps in ISO 8601 format
- Special characters limited to: `# $ % - . / ^ _ { }`

---

## Sources

This comprehensive data model was compiled from the following AWS Supply Chain documentation:

- [Data entities and columns used in AWS Supply Chain](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/data-model.html)
- [Data entities supported in AWS Supply Chain](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/data-model-asc.html)
- [Supply Planning entities](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/entities-supply-planning.html)
- [Planning configuration data](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html)
- [Transactional data](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/transactional.html)
- Individual entity documentation pages for each of the 35+ entities

**Last Updated**: 2026-01-09
**Documentation Version**: Current as of January 2026

---

*End of AWS Supply Chain Data Model Documentation*
