# TMS Vendor UI Research — Actionable Findings

**Date:** 2026-04-09
**Sources:** project44 Movement, FourKites Dynamic Yard, Descartes, Turvo, MercuryGate, Blue Yonder, Oracle OTM

---

## Key Findings by Functional Area

### 1. Control Tower / Dashboard
- **Pattern:** 4-panel layout — KPI strip (5-7 tiles), center map, exception queue, filterable shipment list
- **Role-based defaults:** Dispatchers see exceptions first, managers see KPIs, finance sees cost
- **project44/FourKites:** Customizable widget dashboards ("My Workspace")

### 2. Map Visualization
- **All vendors center on full-width interactive map** as primary operational view
- **project44:** Color-coded pins by status, door-to-door multimodal timeline on click, disruption overlays with impact radius, GPS breadcrumb trail, AI-powered ETAs with influencing factors
- **FourKites:** Yard-level zoom with real-time trailer positions
- **Status colors (industry standard):** Green=on-time, Yellow=at-risk, Red=exception, Gray=not-started, Blue=delivered
- **ETA:** Predictive with confidence scores and influencing factors — maps to our conformal prediction

### 3. Exception Management
- **project44:** Prioritized by business impact (not chronological), inline actions without screen switching, tracked/timestamped/auditable
- **FourKites:** Proactive alerts for detention thresholds, auto-generated tasks by role
- **Pattern:** Priority work list, not notification feed. Each card: shipment, type, impact, customer, carrier, recommended action, time-to-resolve countdown

### 4. Dock Scheduling
- **FourKites leads:** AutoBooker for carrier self-service, calendar-based, auto-reschedule from ETA changes
- **Layout:** Gantt-style door timeline (rows=doors, columns=time, blocks=appointments)
- **KPIs:** Dock utilization %, avg dwell, detention cost, appointment compliance, queue length
- **Role-specific views:** Spotters, dock workers, gate guards, facility managers

### 5. Load Board
- **Turvo:** "3 clicks to manage a shipment" — minimal UI friction
- **MercuryGate:** Historical pattern analysis + current capacity/price trends
- **Waterfall tender:** Ranked carrier list cascading through tiers, real-time accept/reject/timeout status
- **Carrier cards:** Rate, transit time, OTD %, tender accept rate, risk score

### 6. Carrier Scorecard
- **project44 Carrier Assure:** Score displayed at point-of-decision (next to carrier name during selection)
- **Pattern:** Card per carrier, composite score, sparklines for 30/60/90d trends, drill to lane-level

### 7. Cross-Cutting
- **Oracle OTM:** Moving from object-based to workflow-based interfaces
- **Inline actions everywhere:** Act on exceptions without leaving current view
- **Bright colors for alerts only:** Clean base UI, high-contrast for live data
- **Confidence-scored ETAs:** Our unique differentiator if we surface conformal prediction intervals

---

## Priority Implementation Changes

1. **Map-centric control tower** — Full-width map with status-coded shipments + disruption overlays (Phase 7)
2. **Impact-prioritized exception queue with inline actions** — Revise ExceptionDashboard
3. **Gantt-style dock door scheduler** — Revise DockSchedule from CSS grid to Gantt timeline
4. **Waterfall tender visualization** — Revise LoadBoard to show cascade through carrier tiers
5. **Carrier scorecards at point-of-decision** — Integrate into FreightProcurement worklist
6. **Conformal prediction ETA display** — Show P10/P50/P90 intervals on shipment detail
7. **Role-based configurable dashboard widgets** — Future enhancement
