/**
 * Customer Settings Panel
 *
 * Production customer configuration settings including:
 * - Planning Hierarchy Levels (Product, Geography, Time)
 * - Data Sources (SAP, etc.)
 * - Data Import Cadence
 * - CDC Thresholds for Event-Based Planning
 *
 * NOTE: Props use customerId/customerInfo naming.
 * Internally delegates to the implementation which still uses groupId for API compatibility.
 */

export { default } from './GroupSettingsPanel';
