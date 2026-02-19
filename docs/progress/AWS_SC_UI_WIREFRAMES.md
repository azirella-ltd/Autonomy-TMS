# AWS SC UI Wireframes & Feature Screens

**Date**: 2026-01-10
**Status**: Design specification for AWS SC certified features
**Compliance**: 100% AWS SC certified features

---

## Overview

This document provides UI/UX wireframes and design specifications for the AWS Supply Chain certified features implemented in The Beer Game platform. These screens enable management of hierarchical policies, vendor relationships, sourcing schedules, and advanced manufacturing features.

---

## 1. Hierarchical Inventory Policy Management

### Screen: Policy Configuration Wizard

**Location**: Admin → Supply Chain Config → Inventory Policies

**Purpose**: Manage 6-level hierarchical inventory policies with override logic

#### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Inventory Policy Configuration                          [Save]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Policy Hierarchy Level: [Company-wide ▼]                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ ○ Level 1: Company-wide (all products, all sites)        │ │
│  │ ○ Level 2: Segment + Company (e.g., "Retail" segment)    │ │
│  │ ○ Level 3: Geography + Company (e.g., "West Coast")      │ │
│  │ ● Level 4: Segment + Geography + Company                 │ │
│  │ ○ Level 5: Product Group + Segment + Geography + Company │ │
│  │ ○ Level 6: Product + Site (most specific)                │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Policy Details ─────────────────────────────────────────┐  │
│  │                                                            │  │
│  │  Company ID:     [DAYBREAK        ]                       │  │
│  │  Segment:        [RETAIL          ]                       │  │
│  │  Geography:      [WEST_COAST      ]                       │  │
│  │                                                            │  │
│  │  Policy Type:    [abs_level ▼]                           │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │ ○ abs_level    - Absolute inventory level        │   │  │
│  │  │ ○ doc_dem      - Days of coverage (demand)       │   │  │
│  │  │ ● doc_fcst     - Days of coverage (forecast)     │   │  │
│  │  │ ○ sl           - Service level target            │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                            │  │
│  │  Safety Stock:   [15] days    Policy Value: [200] units  │  │
│  │  Reorder Point:  [150] units  Order Quantity: [500] units│  │
│  │                                                            │  │
│  │  Order-Up-To:    [800] units  (for periodic review)      │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Override Preview ──────────────────────────────────────┐   │
│  │ This policy will override:                               │   │
│  │  ✓ Company-wide policy (Level 1)                        │   │
│  │  ✓ Segment-wide policy (Level 2)                        │   │
│  │  ✓ Geography-wide policy (Level 3)                      │   │
│  │                                                           │   │
│  │ This policy will be overridden by:                       │   │
│  │  → Product Group policies (Level 5)                     │   │
│  │  → Product-Site policies (Level 6)                      │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  [View All Policies]  [Test Policy Lookup]  [Apply]  [Cancel]   │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Features

1. **Visual Hierarchy Selector**: Radio buttons showing all 6 levels
2. **Conditional Form Fields**: Show/hide fields based on selected hierarchy level
3. **Policy Type Selector**: 4 AWS SC policy types with descriptions
4. **Override Preview**: Real-time display of what this policy overrides/is overridden by
5. **Validation**: Prevent creation of duplicate policies at same hierarchy level

#### Implementation Notes

**Frontend Components**:
- `PolicyConfigWizard.jsx`: Main form component
- `HierarchyLevelSelector.jsx`: Radio button group with level descriptions
- `PolicyTypeSelector.jsx`: Policy type dropdown with tooltips
- `OverridePreview.jsx`: Visual tree showing policy precedence

**API Endpoints**:
- `POST /api/v1/inv-policy/hierarchical`: Create hierarchical policy
- `GET /api/v1/inv-policy/hierarchy-preview`: Preview override logic
- `GET /api/v1/inv-policy/test-lookup`: Test which policy would apply

---

## 2. Vendor Management System

### Screen: Vendor Product Catalog

**Location**: Admin → Supply Chain Config → Vendor Management

**Purpose**: Manage vendor products, pricing, and lead times

#### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Vendor Product Management                            [+ Add]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Filter by Vendor: [All Vendors ▼]  Product: [All ▼]            │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Vendor              Product        Cost   Lead  Status   │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ 🏭 Global Mfg      Beer Case      $45   7d    [Active]  │●│ │
│  │    ID: 1           ID: 123                              │   │
│  │    Contact: supplier@global.com                         │   │
│  │    Last Updated: 2026-01-08                             │   │
│  │    ───────────────────────────────────────────────────  │   │
│  │                                                           │   │
│  │ 🏭 Local Supplier  Six-Pack       $12   3d    [Active]  │●│ │
│  │    ID: 2           ID: 124                              │   │
│  │    Contact: orders@localsupply.com                      │   │
│  │    Last Updated: 2026-01-09                             │   │
│  │    ───────────────────────────────────────────────────  │   │
│  │                                                           │   │
│  │ 🏭 Premium Co.     Bottle Cap      $0.05 5d   [Active]  │●│ │
│  │    ID: 3           ID: 125                              │   │
│  │    Contact: sales@premiumco.com                         │   │
│  │    Last Updated: 2026-01-10                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  Click any row to edit vendor product details                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Edit Vendor Product: Global Mfg → Beer Case                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Basic Information ─────────────────────────────────────┐    │
│  │                                                           │    │
│  │  Vendor:         [Global Manufacturing      ▼]          │    │
│  │  Product:        [Beer Case (123)           ▼]          │    │
│  │                                                           │    │
│  │  Unit Cost:      [$45.00    ]  Currency: [USD]          │    │
│  │  Lead Time:      [7         ]  days                     │    │
│  │                                                           │    │
│  │  Min Order Qty:  [100       ]  units                    │    │
│  │  Order Multiple: [50        ]  units                    │    │
│  │                                                           │    │
│  │  Status:         ○ Active  ○ Inactive                   │    │
│  │                                                           │    │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Hierarchical Lead Time Overrides ─────────────────────┐     │
│  │                                                           │     │
│  │  Base Lead Time: 7 days (from vendor_product)           │     │
│  │                                                           │     │
│  │  Overrides by Geography:                                │     │
│  │  ┌─────────────────────────────────────────────────┐   │     │
│  │  │ West Coast     → 5 days   [Edit] [Delete]      │   │     │
│  │  │ East Coast     → 9 days   [Edit] [Delete]      │   │     │
│  │  │ International  → 14 days  [Edit] [Delete]      │   │     │
│  │  └─────────────────────────────────────────────────┘   │     │
│  │  [+ Add Geographic Override]                            │     │
│  │                                                           │     │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Usage in Supply Chain ─────────────────────────────────┐    │
│  │                                                           │    │
│  │  Referenced by Sourcing Rules:                          │    │
│  │   • Retailer → Global Mfg (Beer Case)                   │    │
│  │   • Distributor → Global Mfg (Beer Case)                │    │
│  │                                                           │    │
│  │  Historical Orders: 247 orders, avg $11,250/order       │    │
│  │                                                           │    │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [Save Changes]  [Cancel]  [Delete Vendor Product]               │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Features

1. **Vendor Product List**: Filterable table with vendor/product info
2. **Expandable Row Details**: Click to see full contact and update info
3. **Inline Editing**: Edit cost and lead time directly in table
4. **Hierarchical Lead Time Management**: Geographic overrides for lead times
5. **Usage Tracking**: Show which sourcing rules reference this vendor product
6. **Validation**: Prevent duplicate vendor-product combinations

#### Implementation Notes

**Frontend Components**:
- `VendorProductList.jsx`: Main table with filtering
- `VendorProductEditor.jsx`: Edit form modal
- `LeadTimeOverrideManager.jsx`: Hierarchical lead time configuration
- `VendorUsagePanel.jsx`: Shows sourcing rules using this vendor

**API Endpoints**:
- `GET /api/v1/vendor-products`: List all vendor products
- `POST /api/v1/vendor-products`: Create vendor product
- `PUT /api/v1/vendor-products/{id}`: Update vendor product
- `GET /api/v1/vendor-products/{id}/usage`: Get sourcing rules referencing this vendor
- `POST /api/v1/vendor-lead-time-overrides`: Create geographic override

---

## 3. Sourcing Schedule Manager

### Screen: Periodic Ordering Configuration

**Location**: Admin → Supply Chain Config → Sourcing Schedules

**Purpose**: Configure periodic ordering schedules (weekly, monthly, custom dates)

#### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Sourcing Schedule Configuration                      [+ New]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Active Schedules for: Complex_SC                                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                                                           │   │
│  │  📅 Weekly Monday Orders                      [Edit] [×] │   │
│  │     Site: Retailer (Node 7)                              │   │
│  │     Vendor: Global Manufacturing                          │   │
│  │     Schedule: Every Monday                               │   │
│  │     Products: Beer Case (product-level)                  │   │
│  │     Status: Active                                       │   │
│  │                                                           │   │
│  │  ─────────────────────────────────────────────────────   │   │
│  │                                                           │   │
│  │  📅 Monthly First Friday                      [Edit] [×] │   │
│  │     Site: Distributor (Node 5)                           │   │
│  │     Vendor: Local Supplier                               │   │
│  │     Schedule: 1st Friday of each month                   │   │
│  │     Products: All Beverages (product-group-level)        │   │
│  │     Status: Active                                       │   │
│  │                                                           │   │
│  │  ─────────────────────────────────────────────────────   │   │
│  │                                                           │   │
│  │  📅 Bi-Weekly Orders                          [Edit] [×] │   │
│  │     Site: Wholesaler (Node 6)                            │   │
│  │     Schedule: 1st and 3rd Monday                         │   │
│  │     Products: All (company-level)                        │   │
│  │     Status: Active                                       │   │
│  │                                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Create Sourcing Schedule                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Step 1: Basic Information ────────────────────────────┐     │
│  │                                                          │     │
│  │  Schedule ID:    [WEEKLY_MON_RETAILER     ]            │     │
│  │  Description:    [Weekly Monday orders for retailer]   │     │
│  │                                                          │     │
│  │  Destination:    [Retailer (Node 7)       ▼]           │     │
│  │  Source Type:    ○ Buy from Vendor  ○ Transfer         │     │
│  │  Vendor:         [Global Manufacturing    ▼]           │     │
│  │                                                          │     │
│  │  Status:         ☑ Active                              │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Step 2: Schedule Type ─────────────────────────────────┐    │
│  │                                                           │    │
│  │  [Daily] [Weekly] [Monthly] [Custom Dates]              │    │
│  │   ──────  ──────────────────────────────────            │    │
│  │                                                           │    │
│  │  Weekly Schedule Configuration:                          │    │
│  │                                                           │    │
│  │  Order on these days:                                    │    │
│  │  ┌───────────────────────────────────────────────────┐  │    │
│  │  │ □ Sunday                                           │  │    │
│  │  │ ☑ Monday      ← Orders placed every Monday       │  │    │
│  │  │ □ Tuesday                                          │  │    │
│  │  │ □ Wednesday                                        │  │    │
│  │  │ □ Thursday                                         │  │    │
│  │  │ ☑ Friday      ← Also every Friday                 │  │    │
│  │  │ □ Saturday                                         │  │    │
│  │  └───────────────────────────────────────────────────┘  │    │
│  │                                                           │    │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Step 3: Product Hierarchy ────────────────────────────┐     │
│  │                                                          │     │
│  │  Apply schedule to:                                     │     │
│  │  ○ All products (company-wide)                         │     │
│  │  ○ Product group: [Beverages     ▼]                   │     │
│  │  ● Specific product: [Beer Case   ▼]                  │     │
│  │                                                          │     │
│  │  Company ID:       [DAYBREAK]  (optional override)     │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Step 4: Preview & Test ───────────────────────────────┐     │
│  │                                                          │     │
│  │  Test Schedule:  Date: [2026-01-13] (Monday)  [Test]   │     │
│  │                                                          │     │
│  │  Result: ✅ Valid ordering day                          │     │
│  │                                                          │     │
│  │  Upcoming ordering days:                                │     │
│  │   • 2026-01-13 (Monday)                                │     │
│  │   • 2026-01-17 (Friday)                                │     │
│  │   • 2026-01-20 (Monday)                                │     │
│  │   • 2026-01-24 (Friday)                                │     │
│  │   • 2026-01-27 (Monday)                                │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [Back]  [Create Schedule]  [Cancel]                             │
└─────────────────────────────────────────────────────────────────┘
```

#### Monthly Schedule View

```
┌─────────────────────────────────────────────────────────────────┐
│  Monthly Schedule Configuration                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Order frequency: [1st ▼] [Monday ▼] of each month              │
│                    ─────  ────────────────                       │
│                   Week#   Day of Week                             │
│                                                                   │
│  Week Options:                                                    │
│   • 1st week of month                                            │
│   • 2nd week of month                                            │
│   • 3rd week of month                                            │
│   • 4th week of month                                            │
│   • Last week of month (handles 28-31 day months)                │
│                                                                   │
│  Calendar Preview:                                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  January 2026                                            │    │
│  │  Su  Mo  Tu  We  Th  Fr  Sa                             │    │
│  │            1   2   3   4                                 │    │
│  │   5  [6]  7   8   9  10  11   ← 1st Monday = Order day  │    │
│  │  12  13  14  15  16  17  18                             │    │
│  │  19  20  21  22  23  24  25                             │    │
│  │  26  27  28  29  30  31                                 │    │
│  │                                                           │    │
│  │  February 2026                                           │    │
│  │  Su  Mo  Tu  We  Th  Fr  Sa                             │    │
│  │   1  [2]  3   4   5   6   7   ← 1st Monday = Order day  │    │
│  │   8   9  10  11  12  13  14                             │    │
│  │  15  16  17  18  19  20  21                             │    │
│  │  22  23  24  25  26  27  28                             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### Custom Dates View

```
┌─────────────────────────────────────────────────────────────────┐
│  Custom Schedule Configuration                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Specify exact ordering dates:                                    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Date              Reason                    [Add] [×]   │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │  2026-01-15       Start of promotion                [×]  │    │
│  │  2026-02-01       Monthly restock                   [×]  │    │
│  │  2026-02-14       Valentine's Day prep               [×]  │    │
│  │  2026-03-01       End of quarter order               [×]  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  [+ Add Date]  [Import from CSV]  [Generate Pattern]             │
│                                                                   │
│  Pattern Generator:                                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Start Date: [2026-01-01]  End Date: [2026-12-31]      │    │
│  │  Frequency:  Every [2] [weeks ▼]                        │    │
│  │                                                          │    │
│  │  [Generate Dates]                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Features

1. **Schedule Type Tabs**: Daily, Weekly, Monthly, Custom Dates
2. **Visual Day Selector**: Checkbox grid for weekly schedules
3. **Calendar Preview**: Show upcoming ordering days
4. **Test Function**: Validate if specific date is ordering day
5. **Hierarchical Product Assignment**: Company/Product Group/Product level
6. **Pattern Generator**: Auto-generate custom dates with patterns

#### Implementation Notes

**Frontend Components**:
- `SourcingScheduleList.jsx`: List all schedules
- `SourcingScheduleWizard.jsx`: Multi-step creation wizard
- `WeeklyScheduleSelector.jsx`: Day of week checkboxes
- `MonthlyScheduleSelector.jsx`: Week + day dropdowns with calendar preview
- `CustomDateManager.jsx`: Date list with pattern generator
- `ScheduleTestPanel.jsx`: Test if date is valid ordering day

**API Endpoints**:
- `GET /api/v1/sourcing-schedules`: List all schedules
- `POST /api/v1/sourcing-schedules`: Create schedule
- `POST /api/v1/sourcing-schedules/test`: Test if date is valid ordering day
- `GET /api/v1/sourcing-schedules/upcoming-days`: Get next N ordering days

---

## 4. Advanced Manufacturing Features

### Screen: Production Process Configuration

**Location**: Admin → Supply Chain Config → Production Processes

**Purpose**: Configure frozen horizon, setup times, changeover costs, batch sizing

#### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Production Process: Beer Case Manufacturing                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Basic Configuration ──────────────────────────────────┐     │
│  │                                                          │     │
│  │  Process ID:     [BEER_CASE_MFG         ]               │     │
│  │  Description:    [Assemble beer cases from six-packs]   │     │
│  │  Node:           [Factory (Node 4)      ▼]              │     │
│  │                                                          │     │
│  │  Process Time:   [60] minutes per batch                 │     │
│  │  Batch Size:     [100] units                            │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ AWS SC Advanced Features ─────────────────────────────┐     │
│  │                                                          │     │
│  │  🔒 Frozen Horizon                                      │     │
│  │     Lock production orders within: [7] days             │     │
│  │     ℹ Orders within this horizon cannot be changed      │     │
│  │     Use case: Prevent last-minute changes to ensure    │     │
│  │     material availability and resource planning         │     │
│  │                                                          │     │
│  │  ⚙️ Setup & Changeover                                  │     │
│  │     Setup Time:       [30] minutes                      │     │
│  │     Changeover Time:  [45] minutes (between products)   │     │
│  │     Changeover Cost:  [$250.00]                         │     │
│  │     ℹ Setup runs once; changeover when switching SKU    │     │
│  │                                                          │     │
│  │  📦 Batch Size Constraints                              │     │
│  │     Minimum Batch:    [50] units                        │     │
│  │     Maximum Batch:    [500] units                       │     │
│  │     ℹ Production must be within these bounds            │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Impact Analysis ──────────────────────────────────────┐     │
│  │                                                          │     │
│  │  Current Production Schedule:                           │     │
│  │   • 3 orders within frozen horizon (locked)            │     │
│  │   • 7 orders beyond frozen horizon (modifiable)        │     │
│  │                                                          │     │
│  │  Batch Size Violations:                                 │     │
│  │   ⚠ Order #1234: 25 units (below min 50)              │     │
│  │   ⚠ Order #1235: 600 units (above max 500)            │     │
│  │                                                          │     │
│  │  Estimated Changeover Costs (next 30 days):            │     │
│  │   • 12 changeovers × $250 = $3,000                     │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [Save Changes]  [View Production Schedule]  [Cancel]            │
└─────────────────────────────────────────────────────────────────┘
```

### Screen: BOM Alternate Management

**Location**: Admin → Supply Chain Config → Bill of Materials

**Purpose**: Manage component alternates and substitution priorities

#### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Bill of Materials: Beer Case                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Product: Beer Case (Item 123)                                   │
│  Node: Factory (Node 4)                                          │
│                                                                   │
│  ┌─ Component Requirements ───────────────────────────────┐     │
│  │                                                          │     │
│  │  Component          Qty  Alternates        Status       │     │
│  │  ──────────────────────────────────────────────────     │     │
│  │  Six-Pack (124)     4    [2 alternates]    Primary     │●│   │
│  │    ├─ Alt Group A                                       │     │
│  │    │  ├─ Six-Pack (124)       Priority 1 (Primary)     │     │
│  │    │  ├─ Six-Pack Premium     Priority 2               │     │
│  │    │  └─ Six-Pack Budget      Priority 3               │     │
│  │    └─ Substitution Logic: Use highest priority available│     │
│  │                                                          │     │
│  │  Bottle Cap (125)   24   [1 alternate]     Primary     │●│   │
│  │    ├─ Alt Group B                                       │     │
│  │    │  ├─ Bottle Cap (125)     Priority 1 (Primary)     │     │
│  │    │  └─ Bottle Cap Generic   Priority 2 (Fallback)    │     │
│  │    └─ Substitution Logic: Use if primary unavailable    │     │
│  │                                                          │     │
│  │  Cardboard Box (126) 1   [No alternates]   Required    │●│   │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [+ Add Component]  [+ Add Alternate]  [Test BOM Explosion]      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Add Alternate Component                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Primary Component ────────────────────────────────────┐     │
│  │  Component: Six-Pack (124)                              │     │
│  │  Current Alternates: 2 (Six-Pack Premium, Budget)      │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ New Alternate ────────────────────────────────────────┐     │
│  │                                                          │     │
│  │  Alternate Product: [Six-Pack Import   ▼]              │     │
│  │  Alternate Group:   [A] (must match primary)           │     │
│  │  Priority:          [4] (higher = lower priority)      │     │
│  │                                                          │     │
│  │  Quantity Ratio:    [1.0] (1:1 substitution)           │     │
│  │    ℹ 1.0 = direct replacement                           │     │
│  │    2.0 = need 2 alternates for 1 primary               │     │
│  │    0.5 = 1 alternate replaces 2 primary                │     │
│  │                                                          │     │
│  │  Cost Impact:       Primary: $12.00, Alternate: $15.00 │     │
│  │                     Δ +$3.00 per unit (+25%)            │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Substitution Rules ───────────────────────────────────┐     │
│  │                                                          │     │
│  │  When to use this alternate:                            │     │
│  │  ☑ Primary component out of stock                      │     │
│  │  ☑ Primary lead time > 7 days                          │     │
│  │  ☐ Primary cost > $20.00                               │     │
│  │  ☐ Always allow manual selection                       │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ Priority Preview ─────────────────────────────────────┐     │
│  │                                                          │     │
│  │  Current Priority Order (for Alt Group A):              │     │
│  │   1. Six-Pack (124) - Primary                          │     │
│  │   2. Six-Pack Premium                                   │     │
│  │   3. Six-Pack Budget                                    │     │
│  │   4. Six-Pack Import (NEW)                             │     │
│  │                                                          │     │
│  │  System will try components in this order until one     │     │
│  │  is available with acceptable lead time.                │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [Add Alternate]  [Cancel]                                        │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Features

1. **Frozen Horizon Indicator**: Visual timeline showing locked vs modifiable orders
2. **Setup vs Changeover**: Clear distinction with use case descriptions
3. **Batch Size Validation**: Real-time warnings for constraint violations
4. **Cost Impact Analysis**: Calculate changeover costs and savings
5. **Alternate Group Visualization**: Tree view showing priority order
6. **Quantity Ratio Support**: 1:1, 2:1, 0.5:1 substitution ratios
7. **Substitution Rules**: Configurable triggers for alternate usage
8. **BOM Explosion Test**: Validate component availability with alternates

#### Implementation Notes

**Frontend Components**:
- `ProductionProcessEditor.jsx`: Main configuration form
- `FrozenHorizonTimeline.jsx`: Visual timeline of locked orders
- `BatchSizeValidator.jsx`: Real-time constraint checking
- `BOMAlternateTree.jsx`: Hierarchical alternate display
- `AlternateComponentEditor.jsx`: Add/edit alternate with priority
- `SubstitutionRuleConfig.jsx`: Trigger configuration
- `BOMExplosionTester.jsx`: Test component availability

**API Endpoints**:
- `GET /api/v1/production-processes`: List processes
- `PUT /api/v1/production-processes/{id}`: Update advanced features
- `GET /api/v1/production-processes/{id}/frozen-orders`: Get locked orders
- `GET /api/v1/bom/alternates`: Get component alternates
- `POST /api/v1/bom/alternates`: Create alternate
- `POST /api/v1/bom/test-explosion`: Test BOM with alternate logic

---

## 5. Dashboard & Analytics

### Screen: AWS SC Compliance Dashboard

**Location**: Admin → AWS SC Dashboard

**Purpose**: Monitor AWS SC certification status and feature usage

#### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  AWS Supply Chain Certification Dashboard                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  🎉 AWS SC 100% CERTIFIED                               │   │
│  │                                                           │   │
│  │  All 5 priority features implemented and validated       │   │
│  │  Last Validated: 2026-01-10 21:22 UTC                   │   │
│  │  Next Audit: 2026-02-10                                  │   │
│  │                                                           │   │
│  │  [View Validation Report]  [Re-run Validation]           │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Priority 1: Hierarchical Overrides ─────────── 100% ✅ ─┐  │
│  │  ████████████████████████████████████████████████████    │  │
│  │                                                           │  │
│  │  • Nodes: 3/3 hierarchy fields (geo, segment, company)   │  │
│  │  • Items: 1/1 field (product_group_id)                   │  │
│  │  • InvPolicy: 4/4 fields (6-level hierarchy)             │  │
│  │                                                           │  │
│  │  Active Policies by Level:                               │  │
│  │   Level 1 (Company-wide):      50 policies               │  │
│  │   Level 2 (Segment):           30 policies               │  │
│  │   Level 3 (Geography):         20 policies               │  │
│  │   Level 4 (Segment+Geo):       15 policies               │  │
│  │   Level 5 (Product Group):     40 policies               │  │
│  │   Level 6 (Product+Site):      1430 policies             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Priority 2: Policy Types ──────────────────── 100% ✅ ─┐   │
│  │  ████████████████████████████████████████████████████    │   │
│  │                                                           │   │
│  │  Policy Distribution:                                     │   │
│  │   • abs_level (Absolute): 1430 policies (97.5%)          │   │
│  │   • doc_dem (Days Demand): 30 policies (2.0%)            │   │
│  │   • doc_fcst (Days Forecast): 30 policies (2.0%)         │   │
│  │   • sl (Service Level): 30 policies (2.0%)               │   │
│  │                                                           │   │
│  │  [View Policy Analytics]                                  │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Priority 3: Vendor Management ─────────────── 100% ✅ ─┐   │
│  │  ████████████████████████████████████████████████████    │   │
│  │                                                           │   │
│  │  • Vendors (TradingPartners): 3 active                   │   │
│  │  • Vendor Products: 3 catalogued                         │   │
│  │  • Sourcing Rules with Vendor FKs: 15 rules              │   │
│  │  • Lead Time Overrides: 9 geographic overrides           │   │
│  │                                                           │   │
│  │  Cost Savings: $2,450 (vendor optimization)              │   │
│  │  [View Vendor Performance]                                │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Priority 4: Sourcing Schedules ────────────── 100% ✅ ─┐   │
│  │  ████████████████████████████████████████████████████    │   │
│  │                                                           │   │
│  │  • Active Schedules: 5 schedules                         │   │
│  │  • Schedule Types:                                        │   │
│  │    - Weekly: 3 schedules                                 │   │
│  │    - Monthly: 1 schedule                                 │   │
│  │    - Custom: 1 schedule                                  │   │
│  │  • Products on Periodic Review: 45 products              │   │
│  │                                                           │   │
│  │  Order Consolidation: 35% reduction in order frequency   │   │
│  │  [View Schedule Calendar]                                 │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Priority 5: Advanced Features ─────────────── 100% ✅ ─┐   │
│  │  ████████████████████████████████████████████████████    │   │
│  │                                                           │   │
│  │  • Production Processes: 12 processes                    │   │
│  │  • Frozen Horizons: 8 processes (avg 7 days)            │   │
│  │  • Setup/Changeover: 12 processes configured             │   │
│  │  • Batch Constraints: 12 processes (min/max set)         │   │
│  │  • BOM Alternates: 24 alternate components               │   │
│  │                                                           │   │
│  │  Stability: 95% orders within frozen horizon (locked)    │   │
│  │  [View Manufacturing Analytics]                           │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ System Health ────────────────────────────────────────┐     │
│  │                                                          │     │
│  │  Database:    ✅ Migrations current (20260110_advanced) │     │
│  │  Constraints: ✅ 19 FK constraints validated             │     │
│  │  Indexes:     ✅ 11 performance indexes active           │     │
│  │  Data:        ✅ All tables seeded with examples         │     │
│  │                                                          │     │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [Export Compliance Report]  [Schedule Audit]  [View Docs]       │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Features

1. **Compliance Progress Bars**: Visual indicators for each priority
2. **Real-time Metrics**: Count of active policies, vendors, schedules
3. **Business Impact**: Cost savings, order reduction, stability metrics
4. **System Health**: Migration status, constraints, indexes
5. **Drill-down Links**: Navigate to detailed views for each priority
6. **Export Reports**: Generate PDF/Excel compliance reports

#### Implementation Notes

**Frontend Components**:
- `AWSComplianceDashboard.jsx`: Main dashboard
- `ComplianceProgressCard.jsx`: Per-priority status card
- `SystemHealthPanel.jsx`: Database and constraint status
- `ComplianceReportExporter.jsx`: PDF/Excel generation

**API Endpoints**:
- `GET /api/v1/aws-sc/compliance-status`: Get overall compliance metrics
- `GET /api/v1/aws-sc/priority-details/{priority}`: Get priority-specific metrics
- `POST /api/v1/aws-sc/validate`: Re-run validation script
- `GET /api/v1/aws-sc/export-report`: Generate compliance report

---

## 6. Common UI Patterns

### Pattern: Hierarchical Level Indicator

Visual indicator showing which hierarchy level a policy operates at:

```
┌─────────────────────────────────────────────────────────┐
│  Policy Level:  ■ ■ ■ ■ □ □                            │
│                 │ │ │ │ └─ Product Group                │
│                 │ │ │ └─── Segment + Geo                │
│                 │ │ └───── Geography                     │
│                 │ └─────── Segment                       │
│                 └───────── Company                       │
│                                                          │
│  This policy applies at Level 4 (Segment + Geography)   │
│  and will override 3 higher-level policies.             │
└──────────────────────────────────────────────────────────┘
```

### Pattern: Override Chain Visualization

Show policy precedence in a tree structure:

```
Company-wide (Level 1)
  └─ Overridden by ▼
      ├─ Retail Segment (Level 2)
      │   └─ Overridden by ▼
      │       └─ West Coast + Retail (Level 4) ← YOU ARE HERE
      │           └─ Overridden by ▼
      │               └─ Beer Case + Retailer Site (Level 6)
      │
      └─ Wholesale Segment (Level 2)
          └─ Not overridden (in effect)
```

### Pattern: Schedule Test Widget

Inline widget for testing sourcing schedules:

```
┌────────────────────────────────────────────────┐
│  Test Schedule:                                 │
│  Date: [2026-01-13 ▼]  [Test]                  │
│                                                 │
│  Result: ✅ Valid ordering day (Monday)         │
│                                                 │
│  Reason: Matches day_of_week=1 rule for        │
│  product Beer Case (ID: 123)                   │
└─────────────────────────────────────────────────┘
```

### Pattern: Cost Impact Badge

Show cost implications of decisions:

```
┌────────────────────────────────┐
│  Vendor: Global Manufacturing  │
│  Unit Cost: $45.00             │
│                                 │
│  vs. Local Supplier: $48.00    │
│  Savings: $3.00/unit (-6.7%)  │
│  ✅ Current choice is optimal  │
└─────────────────────────────────┘
```

---

## 7. Responsive Design Notes

### Mobile View Adaptations

1. **Hierarchical Policy Form**: Stack fields vertically, use expandable sections
2. **Vendor Product List**: Card view instead of table
3. **Schedule Calendar**: Single month view with swipe navigation
4. **BOM Tree**: Collapsible accordion instead of tree
5. **Dashboard**: Single-column stack with priority cards

### Accessibility

1. **ARIA Labels**: All form fields have descriptive labels
2. **Keyboard Navigation**: Tab order follows logical flow
3. **Screen Reader Support**: Status indicators read as text
4. **Color Contrast**: WCAG AA compliance for all text
5. **Focus Indicators**: Clear visual focus on interactive elements

---

## 8. Integration with Existing UI

### Navigation Updates

Add new menu items under "Supply Chain Config":

```
Admin
  └─ Supply Chain Config
      ├─ Overview (existing)
      ├─ Network Topology (existing)
      ├─ Inventory Policies (NEW - hierarchical UI)
      ├─ Vendor Management (NEW)
      ├─ Sourcing Schedules (NEW)
      ├─ Production Processes (NEW - advanced features)
      ├─ Bill of Materials (NEW - alternates UI)
      └─ AWS SC Dashboard (NEW - compliance status)
```

### Quick Actions Bar

Add shortcuts to dashboard for common tasks:

```
┌───────────────────────────────────────────────────────────┐
│  Quick Actions:                                            │
│  [+ Policy] [+ Vendor] [+ Schedule] [View Compliance]      │
└────────────────────────────────────────────────────────────┘
```

---

## Implementation Recommendations

### Phase 1: Core CRUD Screens (Week 1-2)
1. Vendor Product List & Editor
2. Sourcing Schedule List & Creator
3. Production Process Editor (advanced fields)

### Phase 2: Advanced Features (Week 3-4)
4. Hierarchical Policy Wizard
5. BOM Alternate Manager
6. Schedule Testing & Preview

### Phase 3: Analytics & Reporting (Week 5-6)
7. AWS SC Compliance Dashboard
8. Cost Impact Analytics
9. Override Chain Visualizations

### Phase 4: Polish & Testing (Week 7-8)
10. Mobile responsive layouts
11. Accessibility audit & fixes
12. User acceptance testing
13. Documentation & training materials

---

## Technical Stack Recommendations

**Frontend**:
- React 18 with Material-UI 5 (consistent with existing UI)
- React Hook Form for complex forms
- React Query for API state management
- Recharts for analytics visualizations
- date-fns for date handling in schedules

**Backend API Extensions**:
- FastAPI endpoints for all CRUD operations
- Pydantic models for request/response validation
- Async SQLAlchemy queries for performance
- Background tasks for validation runs

**Testing**:
- Jest + React Testing Library for component tests
- Cypress for E2E testing of workflows
- API integration tests with pytest

---

## Conclusion

These wireframes provide comprehensive UI specifications for all AWS Supply Chain certified features. The design prioritizes:

1. **Clarity**: Complex hierarchical logic presented visually
2. **Validation**: Real-time feedback on constraint violations
3. **Guidance**: Contextual help and examples throughout
4. **Efficiency**: Quick actions and shortcuts for common tasks
5. **Visibility**: Compliance dashboard shows certification status

**Next Steps**: Begin Phase 1 implementation with vendor management and sourcing schedule screens, as these have the highest user impact and simplest data models.

---

## Document Version

- **Version**: 1.0
- **Last Updated**: 2026-01-10
- **Author**: Claude (Autonomy AWS SC Certification Team)
- **Status**: Ready for UI development kickoff
