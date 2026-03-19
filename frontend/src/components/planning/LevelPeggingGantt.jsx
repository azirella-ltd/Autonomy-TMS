/**
 * LevelPeggingGantt — D3-based Gantt chart for multi-level BOM pegging visualization
 *
 * Shows how demand is satisfied through the full pegging tree (multi-level BOM).
 * Each row represents a product at a BOM level, with bars showing supply sources
 * (PO, MO, TO, on-hand, in-transit) spanning their lead-time windows.
 *
 * Props:
 *   configId       - Supply chain config ID
 *   productId      - Product ID at the demand level
 *   siteId         - Site ID where demand occurs
 *   demandDate     - ISO date string for the demand bucket
 *   demandType     - Optional: CUSTOMER_ORDER, FORECAST
 *   demandId       - Optional: specific demand record ID
 *   onClose        - Close handler
 */

import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import PropTypes from 'prop-types';
import * as d3 from 'd3';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Spinner,
} from '../common';
import { X } from 'lucide-react';
import { api } from '../../services/api';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const BAR_COLORS = {
  po_request: '#1976D2',
  mo_request: '#388E3C',
  to_request: '#F57C00',
  on_hand: '#9E9E9E',
  in_transit: '#7B1FA2',
  planned_order: '#0097A7',
  shortfall: '#D32F2F',
};

const BAR_LABELS = {
  po_request: 'PO',
  mo_request: 'MO',
  to_request: 'TO',
  on_hand: 'On Hand',
  in_transit: 'In Transit',
  planned_order: 'Planned',
  shortfall: 'Shortfall',
};

const ROW_HEIGHT = 40;
const MARGIN = { top: 30, right: 20, bottom: 30, left: 10 };
const BAR_HEIGHT = 24;
const BAR_Y_OFFSET = (ROW_HEIGHT - BAR_HEIGHT) / 2;

const LevelPeggingGantt = ({
  configId,
  productId,
  siteId,
  demandDate,
  demandType,
  demandId,
  onClose,
}) => {
  const { formatProduct, formatSite } = useDisplayPreferences();
  const svgRef = useRef(null);
  const svgContainerRef = useRef(null);
  const tooltipRef = useRef(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [ganttData, setGanttData] = useState(null);
  const [highlightedChain, setHighlightedChain] = useState(null);

  // Fetch pegging gantt data
  useEffect(() => {
    if (!configId || !productId || !siteId || !demandDate) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = {};
        if (demandDate) params.demand_date = demandDate;
        if (demandType) params.demand_type = demandType;
        if (demandId) params.demand_id = demandId;

        const response = await api.get(
          `/pegging/gantt/${configId}/${encodeURIComponent(productId)}/${siteId}`,
          { params }
        );
        setGanttData(response.data);
      } catch (err) {
        console.error('Failed to fetch pegging data:', err);
        setError('Failed to load pegging data. The pegging API may not be available yet.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [configId, productId, siteId, demandDate, demandType, demandId]);

  const ganttRows = useMemo(() => {
    if (!ganttData?.rows) return [];
    return ganttData.rows;
  }, [ganttData]);

  const summaryInfo = useMemo(() => {
    if (!ganttData) return { totalDemand: 0, totalPegged: 0, unpegged: 0 };
    return {
      totalDemand: ganttData.total_demand || 0,
      totalPegged: ganttData.total_pegged || 0,
      unpegged: (ganttData.total_demand || 0) - (ganttData.total_pegged || 0),
      productName: ganttData.product_name || productId,
      siteName: ganttData.site_name || siteId,
    };
  }, [ganttData, productId, siteId]);

  // Show tooltip
  const showTooltip = useCallback((event, bar) => {
    const tooltip = tooltipRef.current;
    if (!tooltip) return;

    const lines = [];
    lines.push(`<strong>${BAR_LABELS[bar.supply_type] || bar.supply_type}</strong>`);
    if (bar.supply_id) lines.push(`ID: ${bar.supply_id}`);
    lines.push(`Qty: ${(bar.quantity || 0).toLocaleString()}`);
    if (bar.bar_start && bar.bar_end) {
      lines.push(`${new Date(bar.bar_start).toLocaleDateString()} - ${new Date(bar.bar_end).toLocaleDateString()}`);
    }
    if (bar.lead_time_days != null) {
      let ltText = `Lead Time: ${bar.lead_time_days}d`;
      if (bar.lead_time_lower != null && bar.lead_time_upper != null) {
        ltText += ` [${bar.lead_time_lower}d - ${bar.lead_time_upper}d]`;
      }
      lines.push(ltText);
    }
    if (bar.source_site) lines.push(`Source: ${bar.source_site}`);
    if (bar.supplier) lines.push(`Supplier: ${bar.supplier}`);
    if (bar.pegging_status) lines.push(`Status: ${bar.pegging_status}`);
    if (bar.chain_id) lines.push(`Chain: ${bar.chain_id}`);

    tooltip.innerHTML = lines.join('<br/>');
    tooltip.style.display = 'block';
    tooltip.style.left = `${event.pageX + 12}px`;
    tooltip.style.top = `${event.pageY - 10}px`;
  }, []);

  const hideTooltip = useCallback(() => {
    const tooltip = tooltipRef.current;
    if (tooltip) tooltip.style.display = 'none';
  }, []);

  // D3 rendering
  useEffect(() => {
    if (!svgRef.current || ganttRows.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    // Collect all dates from bars to determine time range
    const allDates = [];
    const needByDate = new Date(demandDate);
    allDates.push(needByDate);

    ganttRows.forEach((row) => {
      (row.bars || []).forEach((bar) => {
        if (bar.bar_start) allDates.push(new Date(bar.bar_start));
        if (bar.bar_end) allDates.push(new Date(bar.bar_end));
        if (bar.lead_time_lower != null && bar.bar_start) {
          // Extend range for conformal bands
          const start = new Date(bar.bar_start);
          const lowerStart = new Date(start);
          lowerStart.setDate(lowerStart.getDate() - (bar.lead_time_upper - bar.lead_time_days || 0));
          allDates.push(lowerStart);
        }
      });
    });

    if (allDates.length < 2) {
      // Add some default range around the demand date
      const before = new Date(needByDate);
      before.setDate(before.getDate() - 30);
      const after = new Date(needByDate);
      after.setDate(after.getDate() + 7);
      allDates.push(before, after);
    }

    const minDate = d3.min(allDates);
    const maxDate = d3.max(allDates);

    // Add padding to dates
    const paddedMin = new Date(minDate);
    paddedMin.setDate(paddedMin.getDate() - 3);
    const paddedMax = new Date(maxDate);
    paddedMax.setDate(paddedMax.getDate() + 3);

    const chartHeight = ganttRows.length * ROW_HEIGHT;
    const containerWidth = svgContainerRef.current?.clientWidth || 800;
    const chartWidth = Math.max(containerWidth - MARGIN.left - MARGIN.right, 400);
    const totalWidth = chartWidth + MARGIN.left + MARGIN.right;
    const totalHeight = chartHeight + MARGIN.top + MARGIN.bottom;

    svg.attr('width', totalWidth).attr('height', totalHeight);

    const g = svg
      .append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`);

    // X scale
    const xScale = d3
      .scaleTime()
      .domain([paddedMin, paddedMax])
      .range([0, chartWidth]);

    // X axis
    g.append('g')
      .attr('transform', `translate(0,${chartHeight})`)
      .call(
        d3
          .axisBottom(xScale)
          .ticks(d3.timeWeek.every(1))
          .tickFormat(d3.timeFormat('%b %d'))
      )
      .selectAll('text')
      .attr('font-size', '10px')
      .attr('transform', 'rotate(-30)')
      .attr('text-anchor', 'end');

    // Top axis (light)
    g.append('g')
      .call(
        d3
          .axisTop(xScale)
          .ticks(d3.timeMonth.every(1))
          .tickFormat(d3.timeFormat('%B %Y'))
      )
      .selectAll('text')
      .attr('font-size', '10px');

    // Row backgrounds (alternating)
    ganttRows.forEach((_, i) => {
      if (i % 2 === 0) {
        g.append('rect')
          .attr('x', 0)
          .attr('y', i * ROW_HEIGHT)
          .attr('width', chartWidth)
          .attr('height', ROW_HEIGHT)
          .attr('fill', 'rgba(0,0,0,0.02)');
      }
    });

    // Vertical "need by" line at demand date
    const needByX = xScale(needByDate);
    g.append('line')
      .attr('x1', needByX)
      .attr('y1', 0)
      .attr('x2', needByX)
      .attr('y2', chartHeight)
      .attr('stroke', '#D32F2F')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '6,3');

    g.append('text')
      .attr('x', needByX + 4)
      .attr('y', -4)
      .attr('fill', '#D32F2F')
      .attr('font-size', '10px')
      .attr('font-weight', 'bold')
      .text('Need By');

    // Draw bars for each row
    ganttRows.forEach((row, rowIdx) => {
      const rowY = rowIdx * ROW_HEIGHT;
      const bars = row.bars || [];

      bars.forEach((bar) => {
        const supplyType = bar.supply_type || 'planned_order';
        const color = BAR_COLORS[supplyType] || BAR_COLORS.planned_order;
        const isHighlighted =
          highlightedChain == null || bar.chain_id === highlightedChain;
        const opacity = highlightedChain == null ? 1 : isHighlighted ? 1 : 0.2;

        if (supplyType === 'on_hand') {
          // On-hand: narrow fixed-width rectangle at demand date position
          const ohWidth = 12;
          const ohX = needByX - ohWidth - 2;
          g.append('rect')
            .attr('x', ohX)
            .attr('y', rowY + BAR_Y_OFFSET)
            .attr('width', ohWidth)
            .attr('height', BAR_HEIGHT)
            .attr('rx', 3)
            .attr('fill', color)
            .attr('opacity', opacity)
            .attr('cursor', 'pointer')
            .on('mousemove', (event) => showTooltip(event, bar))
            .on('mouseleave', hideTooltip)
            .on('click', () => {
              setHighlightedChain((prev) =>
                prev === bar.chain_id ? null : bar.chain_id
              );
            });

          // Quantity label above on-hand bar
          g.append('text')
            .attr('x', ohX + ohWidth / 2)
            .attr('y', rowY + BAR_Y_OFFSET - 2)
            .attr('text-anchor', 'middle')
            .attr('fill', '#666')
            .attr('font-size', '9px')
            .attr('opacity', opacity)
            .text(bar.quantity != null ? bar.quantity.toLocaleString() : '');
        } else if (supplyType === 'shortfall') {
          // Shortfall indicator: red diamond/triangle at need-by line
          const sfX = needByX + 4;
          g.append('rect')
            .attr('x', sfX)
            .attr('y', rowY + BAR_Y_OFFSET + 4)
            .attr('width', BAR_HEIGHT - 8)
            .attr('height', BAR_HEIGHT - 8)
            .attr('rx', 2)
            .attr('fill', BAR_COLORS.shortfall)
            .attr('opacity', opacity)
            .attr('cursor', 'pointer')
            .on('mousemove', (event) => showTooltip(event, bar))
            .on('mouseleave', hideTooltip);

          g.append('text')
            .attr('x', sfX + (BAR_HEIGHT - 8) + 4)
            .attr('y', rowY + BAR_Y_OFFSET + BAR_HEIGHT / 2 + 3)
            .attr('fill', BAR_COLORS.shortfall)
            .attr('font-size', '9px')
            .attr('font-weight', 'bold')
            .attr('opacity', opacity)
            .text(`-${Math.abs(bar.quantity || 0).toLocaleString()}`);
        } else {
          // Standard supply bar spanning bar_start -> bar_end
          const barStart = bar.bar_start ? new Date(bar.bar_start) : paddedMin;
          const barEnd = bar.bar_end ? new Date(bar.bar_end) : needByDate;
          const x1 = xScale(barStart);
          const x2 = xScale(barEnd);
          const barWidth = Math.max(x2 - x1, 4);

          // Conformal uncertainty band (if available)
          if (
            bar.lead_time_lower != null &&
            bar.lead_time_upper != null &&
            bar.lead_time_days != null
          ) {
            const ltDiff = bar.lead_time_upper - bar.lead_time_lower;
            if (ltDiff > 0) {
              const confStart = new Date(barEnd);
              confStart.setDate(
                confStart.getDate() -
                  (bar.lead_time_upper - bar.lead_time_days)
              );
              const confEnd = new Date(barEnd);
              confEnd.setDate(
                confEnd.getDate() +
                  (bar.lead_time_days - bar.lead_time_lower)
              );
              const cx1 = xScale(confStart);
              const cx2 = xScale(confEnd);

              g.append('rect')
                .attr('x', Math.min(cx1, cx2))
                .attr('y', rowY + BAR_Y_OFFSET - 2)
                .attr('width', Math.abs(cx2 - cx1))
                .attr('height', BAR_HEIGHT + 4)
                .attr('rx', 3)
                .attr('fill', color)
                .attr('opacity', 0.12 * opacity);
            }
          }

          // Main bar
          g.append('rect')
            .attr('x', x1)
            .attr('y', rowY + BAR_Y_OFFSET)
            .attr('width', barWidth)
            .attr('height', BAR_HEIGHT)
            .attr('rx', 3)
            .attr('fill', color)
            .attr('opacity', opacity * 0.85)
            .attr('stroke', isHighlighted && highlightedChain != null ? '#000' : 'none')
            .attr('stroke-width', isHighlighted && highlightedChain != null ? 1.5 : 0)
            .attr('cursor', 'pointer')
            .on('mousemove', (event) => showTooltip(event, bar))
            .on('mouseleave', hideTooltip)
            .on('click', () => {
              setHighlightedChain((prev) =>
                prev === bar.chain_id ? null : bar.chain_id
              );
            });

          // Quantity label inside bar (or above if too narrow)
          const label = bar.quantity != null ? bar.quantity.toLocaleString() : '';
          const labelWidth = label.length * 6;
          if (barWidth > labelWidth + 8) {
            g.append('text')
              .attr('x', x1 + barWidth / 2)
              .attr('y', rowY + BAR_Y_OFFSET + BAR_HEIGHT / 2 + 4)
              .attr('text-anchor', 'middle')
              .attr('fill', '#fff')
              .attr('font-size', '10px')
              .attr('font-weight', 'bold')
              .attr('opacity', opacity)
              .attr('pointer-events', 'none')
              .text(label);
          } else {
            g.append('text')
              .attr('x', x1 + barWidth / 2)
              .attr('y', rowY + BAR_Y_OFFSET - 2)
              .attr('text-anchor', 'middle')
              .attr('fill', '#666')
              .attr('font-size', '9px')
              .attr('opacity', opacity)
              .attr('pointer-events', 'none')
              .text(label);
          }
        }
      });
    });
  }, [ganttRows, demandDate, highlightedChain, showTooltip, hideTooltip]);

  const formattedDemandDate = useMemo(() => {
    try {
      return new Date(demandDate).toLocaleDateString();
    } catch {
      return demandDate;
    }
  }, [demandDate]);

  return (
    <Card className="mt-4">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">
              Level Pegging: {summaryInfo.productName} @ {summaryInfo.siteName} — {formattedDemandDate}
            </CardTitle>
            <div className="flex gap-4 mt-1 text-sm text-muted-foreground">
              <span>Total Demand: <strong>{summaryInfo.totalDemand.toLocaleString()}</strong></span>
              <span>Pegged: <strong>{summaryInfo.totalPegged.toLocaleString()}</strong></span>
              {summaryInfo.unpegged > 0 && (
                <span className="text-red-600">
                  Unpegged: <strong>{summaryInfo.unpegged.toLocaleString()}</strong>
                </span>
              )}
            </div>
          </div>
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Spinner className="mr-2" />
            <span className="text-muted-foreground">Loading pegging data...</span>
          </div>
        )}

        {error && (
          <div className="text-center py-8 text-muted-foreground">
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && ganttRows.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            No pegging data available for this demand bucket.
          </div>
        )}

        {!loading && !error && ganttRows.length > 0 && (
          <>
            <div className="flex">
              {/* Left panel: BOM tree labels */}
              <div className="w-64 flex-shrink-0 border-r border-border">
                {/* Header spacer matching top axis */}
                <div style={{ height: MARGIN.top }} className="flex items-end pb-1">
                  <span className="text-xs font-medium text-muted-foreground pl-2">Product / Component</span>
                </div>
                {ganttRows.map((row, idx) => (
                  <div
                    key={idx}
                    style={{ paddingLeft: (row.bom_level || 0) * 24, height: ROW_HEIGHT }}
                    className="flex items-center pr-2"
                  >
                    {(row.bom_level || 0) > 0 && (
                      <span className="text-muted-foreground mr-1 text-xs">&#x2514;</span>
                    )}
                    <span className="font-medium text-sm truncate">
                      {formatProduct(row.product_id, row.product_name)}
                    </span>
                    {row.bom_quantity != null && row.bom_quantity !== 1 && (
                      <Badge variant="secondary" className="ml-1 text-xs px-1 py-0">
                        x{row.bom_quantity}
                      </Badge>
                    )}
                  </div>
                ))}
                {/* Bottom spacer matching bottom axis */}
                <div style={{ height: MARGIN.bottom }} />
              </div>

              {/* Right panel: D3 Gantt chart */}
              <div className="flex-1 overflow-x-auto" ref={svgContainerRef}>
                <svg ref={svgRef} />
              </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-4 mt-4 text-xs text-muted-foreground border-t border-border pt-3">
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.po_request }}
                />
                PO
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.mo_request }}
                />
                MO
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.to_request }}
                />
                TO
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.on_hand }}
                />
                On Hand
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.in_transit }}
                />
                In Transit
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.planned_order }}
                />
                Planned
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ background: BAR_COLORS.shortfall }}
                />
                Shortfall
              </span>
              {highlightedChain && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs h-5 px-2"
                  onClick={() => setHighlightedChain(null)}
                >
                  Clear chain highlight
                </Button>
              )}
            </div>
          </>
        )}

        {/* Tooltip (portal-like, positioned absolutely) */}
        <div
          ref={tooltipRef}
          style={{
            display: 'none',
            position: 'fixed',
            zIndex: 9999,
            background: 'rgba(0,0,0,0.85)',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontSize: '12px',
            lineHeight: '1.5',
            pointerEvents: 'none',
            maxWidth: '300px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          }}
        />
      </CardContent>
    </Card>
  );
};

LevelPeggingGantt.propTypes = {
  configId: PropTypes.number.isRequired,
  productId: PropTypes.string.isRequired,
  siteId: PropTypes.number.isRequired,
  demandDate: PropTypes.string.isRequired,
  demandType: PropTypes.string,
  demandId: PropTypes.string,
  onClose: PropTypes.func,
};

export default LevelPeggingGantt;
