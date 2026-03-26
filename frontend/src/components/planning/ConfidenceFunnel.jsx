/**
 * ConfidenceFunnel — D3-based nested probability bar visualization
 *
 * Shows when supply orders will actually arrive using conformal prediction
 * intervals. Each order is rendered as nested horizontal bars at P50/P80/P90/P95
 * confidence levels, with target date markers and on-time probability.
 *
 * Props:
 *   configId     - Supply chain config ID
 *   productId    - Product ID
 *   siteId       - Site ID where supply is received
 *   horizonDays  - Planning horizon in days (default 90)
 *   onClose      - Close handler
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
import { X, AlertTriangle, CheckCircle } from 'lucide-react';
import { api } from '../../services/api';

// Color base per order type (same scheme as LevelPeggingGantt)
const TYPE_COLORS = {
  po_request: '#1976D2',
  mo_request: '#388E3C',
  to_request: '#F57C00',
  planned_order: '#0097A7',
};

const TYPE_LABELS = {
  po_request: 'PO',
  mo_request: 'MO',
  to_request: 'TO',
  planned_order: 'Planned',
};

// Opacity per confidence level (outermost = lightest)
const LEVEL_OPACITY = {
  p95: 0.15,
  p90: 0.30,
  p80: 0.50,
  p50: 0.85,
};

const LEVEL_LABELS = {
  p50: '50%',
  p80: '80%',
  p90: '90%',
  p95: '95%',
};

const ROW_HEIGHT = 48;
const MARGIN = { top: 36, right: 24, bottom: 32, left: 10 };
const BAR_HEIGHTS = {
  p95: 36,
  p90: 28,
  p80: 20,
  p50: 12,
};

const ConfidenceFunnel = ({
  configId,
  productId,
  siteId,
  horizonDays = 90,
  onClose,
}) => {
  const svgRef = useRef(null);
  const svgContainerRef = useRef(null);
  const tooltipRef = useRef(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  // Fetch data
  useEffect(() => {
    if (!configId || !productId || !siteId) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await api.get(
          `/pegging/confidence-funnel/${configId}/${encodeURIComponent(productId)}/${siteId}`,
          { params: { horizon_days: horizonDays } }
        );
        setData(response.data);
      } catch (err) {
        console.error('Failed to fetch confidence funnel data:', err);
        setError('Failed to load confidence funnel data.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [configId, productId, siteId, horizonDays]);

  const orders = useMemo(() => data?.orders || [], [data]);
  const summary = useMemo(() => data?.summary || {}, [data]);

  // Tooltip handlers
  const showTooltip = useCallback((event, order) => {
    const tooltip = tooltipRef.current;
    if (!tooltip) return;

    const lines = [];
    lines.push(`<strong>${order.order_id}</strong> (${TYPE_LABELS[order.order_type] || order.order_type})`);
    lines.push(`Qty: ${(order.quantity || 0).toLocaleString()}`);
    if (order.source) lines.push(`Source: ${order.source}`);
    lines.push(`Planned: ${order.planned_receipt || 'N/A'}`);
    if (order.target_date) lines.push(`Target: ${order.target_date}`);
    lines.push(`On-time: ${(order.on_time_probability * 100).toFixed(0)}%`);

    const intervals = order.intervals || {};
    lines.push('');
    lines.push('<span style="opacity:0.7">Confidence Intervals:</span>');
    ['p50', 'p80', 'p90', 'p95'].forEach((level) => {
      const iv = intervals[level];
      if (iv && iv[0] && iv[1]) {
        lines.push(
          `&nbsp;&nbsp;${LEVEL_LABELS[level]}: ${new Date(iv[0]).toLocaleDateString()} - ${new Date(iv[1]).toLocaleDateString()}`
        );
      }
    });

    if (order.has_conformal) {
      lines.push('<span style="color:#4CAF50">Conformal intervals available</span>');
    } else {
      lines.push('<span style="color:#FF9800">Heuristic intervals (no conformal data)</span>');
    }

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
    if (!svgRef.current || orders.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    // Collect all dates for scale
    const allDates = [new Date()];
    orders.forEach((order) => {
      if (order.planned_receipt) allDates.push(new Date(order.planned_receipt));
      if (order.target_date) allDates.push(new Date(order.target_date));
      const intervals = order.intervals || {};
      ['p50', 'p80', 'p90', 'p95'].forEach((level) => {
        const iv = intervals[level];
        if (iv && iv[0]) allDates.push(new Date(iv[0]));
        if (iv && iv[1]) allDates.push(new Date(iv[1]));
      });
    });

    const minDate = d3.min(allDates);
    const maxDate = d3.max(allDates);

    // Add padding
    const paddedMin = new Date(minDate);
    paddedMin.setDate(paddedMin.getDate() - 5);
    const paddedMax = new Date(maxDate);
    paddedMax.setDate(paddedMax.getDate() + 5);

    const chartHeight = orders.length * ROW_HEIGHT;
    const containerWidth = svgContainerRef.current?.clientWidth || 800;
    const chartWidth = Math.max(containerWidth - MARGIN.left - MARGIN.right, 400);
    const totalWidth = chartWidth + MARGIN.left + MARGIN.right;
    const totalHeight = chartHeight + MARGIN.top + MARGIN.bottom;

    svg.attr('width', totalWidth).attr('height', totalHeight);

    const g = svg
      .append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`);

    // X scale (time)
    const xScale = d3
      .scaleTime()
      .domain([paddedMin, paddedMax])
      .range([0, chartWidth]);

    // Top axis
    g.append('g')
      .call(
        d3
          .axisTop(xScale)
          .ticks(d3.timeWeek.every(1))
          .tickFormat(d3.timeFormat('%b %d'))
      )
      .selectAll('text')
      .attr('font-size', '10px')
      .attr('transform', 'rotate(-30)')
      .attr('text-anchor', 'start');

    // Bottom axis
    g.append('g')
      .attr('transform', `translate(0,${chartHeight})`)
      .call(
        d3
          .axisBottom(xScale)
          .ticks(d3.timeWeek.every(2))
          .tickFormat(d3.timeFormat('%b %d'))
      )
      .selectAll('text')
      .attr('font-size', '10px')
      .attr('transform', 'rotate(-30)')
      .attr('text-anchor', 'end');

    // "Today" vertical line
    const todayX = xScale(new Date());
    if (todayX >= 0 && todayX <= chartWidth) {
      g.append('line')
        .attr('x1', todayX)
        .attr('y1', 0)
        .attr('x2', todayX)
        .attr('y2', chartHeight)
        .attr('stroke', '#9E9E9E')
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,3');

      g.append('text')
        .attr('x', todayX + 3)
        .attr('y', -6)
        .attr('fill', '#9E9E9E')
        .attr('font-size', '9px')
        .text('Today');
    }

    // Row backgrounds (alternating)
    orders.forEach((_, i) => {
      if (i % 2 === 0) {
        g.append('rect')
          .attr('x', 0)
          .attr('y', i * ROW_HEIGHT)
          .attr('width', chartWidth)
          .attr('height', ROW_HEIGHT)
          .attr('fill', 'rgba(0,0,0,0.02)');
      }
    });

    // Draw each order row
    orders.forEach((order, rowIdx) => {
      const rowY = rowIdx * ROW_HEIGHT;
      const rowCenter = rowY + ROW_HEIGHT / 2;
      const color = TYPE_COLORS[order.order_type] || TYPE_COLORS.planned_order;
      const intervals = order.intervals || {};

      // Draw bars from widest (P95) to narrowest (P50)
      ['p95', 'p90', 'p80', 'p50'].forEach((level) => {
        const iv = intervals[level];
        if (!iv || !iv[0] || !iv[1]) return;

        const x1 = xScale(new Date(iv[0]));
        const x2 = xScale(new Date(iv[1]));
        const barH = BAR_HEIGHTS[level];
        const barY = rowCenter - barH / 2;
        const barW = Math.max(x2 - x1, 2);

        g.append('rect')
          .attr('x', x1)
          .attr('y', barY)
          .attr('width', barW)
          .attr('height', barH)
          .attr('rx', level === 'p50' ? 3 : 4)
          .attr('fill', color)
          .attr('opacity', LEVEL_OPACITY[level])
          .attr('cursor', 'pointer')
          .on('mousemove', (event) => showTooltip(event, order))
          .on('mouseleave', hideTooltip);

        // Stroke on P50 bar for clarity
        if (level === 'p50') {
          g.append('rect')
            .attr('x', x1)
            .attr('y', barY)
            .attr('width', barW)
            .attr('height', barH)
            .attr('rx', 3)
            .attr('fill', 'none')
            .attr('stroke', color)
            .attr('stroke-width', 1.5)
            .attr('opacity', 0.8)
            .attr('pointer-events', 'none');
        }
      });

      // Planned receipt marker (diamond)
      if (order.planned_receipt) {
        const px = xScale(new Date(order.planned_receipt));
        g.append('circle')
          .attr('cx', px)
          .attr('cy', rowCenter)
          .attr('r', 4)
          .attr('fill', color)
          .attr('stroke', '#fff')
          .attr('stroke-width', 1.5)
          .attr('pointer-events', 'none');
      }

      // Target date vertical dashed line
      if (order.target_date) {
        const tx = xScale(new Date(order.target_date));
        const isLate = order.on_time_probability < 0.7;
        const lineColor = isLate ? '#D32F2F' : '#4CAF50';

        g.append('line')
          .attr('x1', tx)
          .attr('y1', rowY + 4)
          .attr('x2', tx)
          .attr('y2', rowY + ROW_HEIGHT - 4)
          .attr('stroke', lineColor)
          .attr('stroke-width', 1.5)
          .attr('stroke-dasharray', '4,2');

        // Small "T" label
        g.append('text')
          .attr('x', tx + 3)
          .attr('y', rowY + 10)
          .attr('fill', lineColor)
          .attr('font-size', '8px')
          .attr('font-weight', 'bold')
          .text('T');
      }
    });
  }, [orders, showTooltip, hideTooltip]);

  // Summary badge color
  const avgOtpColor = useMemo(() => {
    const avg = summary.avg_on_time_probability || 0;
    if (avg >= 0.85) return 'success';
    if (avg >= 0.7) return 'warning';
    return 'destructive';
  }, [summary]);

  return (
    <Card className="mt-4">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">
              Confidence Funnel: {data?.product_name || productId} @ {data?.site_name || siteId}
            </CardTitle>
            {!loading && !error && orders.length > 0 && (
              <div className="flex gap-4 mt-1 text-sm text-muted-foreground">
                <span>
                  {summary.total_orders} order{summary.total_orders !== 1 ? 's' : ''}
                </span>
                <span className="flex items-center gap-1">
                  Avg On-Time:
                  <Badge variant={avgOtpColor}>
                    {((summary.avg_on_time_probability || 0) * 100).toFixed(0)}%
                  </Badge>
                </span>
                {summary.highest_risk_order && (
                  <span className="flex items-center gap-1 text-amber-600">
                    <AlertTriangle className="h-3 w-3" />
                    Highest risk: {summary.highest_risk_order}
                  </span>
                )}
                {summary.critical_path_orders?.length > 0 && (
                  <span className="text-red-600">
                    {summary.critical_path_orders.length} critical
                  </span>
                )}
              </div>
            )}
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
            <span className="text-muted-foreground">Loading confidence data...</span>
          </div>
        )}

        {error && (
          <div className="text-center py-8 text-muted-foreground">
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && orders.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            No supply orders found for this product-site within the horizon.
          </div>
        )}

        {!loading && !error && orders.length > 0 && (
          <>
            <div className="flex">
              {/* Left panel: Order labels */}
              <div className="w-56 flex-shrink-0 border-r border-border">
                {/* Header spacer */}
                <div style={{ height: MARGIN.top }} className="flex items-end pb-1">
                  <span className="text-xs font-medium text-muted-foreground pl-2">
                    Supply Order
                  </span>
                </div>
                {orders.map((order, idx) => (
                  <div
                    key={idx}
                    style={{ height: ROW_HEIGHT }}
                    className="flex items-center px-2 gap-2"
                  >
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-1">
                        <span
                          className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0"
                          style={{
                            background:
                              TYPE_COLORS[order.order_type] || TYPE_COLORS.planned_order,
                          }}
                        />
                        <span className="font-medium text-xs truncate">
                          {order.order_id}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <span>{(order.quantity || 0).toLocaleString()} units</span>
                        {order.source && (
                          <>
                            <span className="text-muted-foreground/50">|</span>
                            <span className="truncate">{order.source}</span>
                          </>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {order.on_time_probability >= 0.85 ? (
                          <CheckCircle className="h-3 w-3 text-green-500" />
                        ) : order.on_time_probability >= 0.7 ? (
                          <CheckCircle className="h-3 w-3 text-amber-500" />
                        ) : (
                          <AlertTriangle className="h-3 w-3 text-red-500" />
                        )}
                        <span
                          className={`text-xs font-medium ${
                            order.on_time_probability >= 0.85
                              ? 'text-green-600'
                              : order.on_time_probability >= 0.7
                              ? 'text-amber-600'
                              : 'text-red-600'
                          }`}
                        >
                          {(order.on_time_probability * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
                {/* Bottom spacer */}
                <div style={{ height: MARGIN.bottom }} />
              </div>

              {/* Right panel: D3 SVG */}
              <div className="flex-1 overflow-x-auto" ref={svgContainerRef}>
                <svg ref={svgRef} />
              </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-4 mt-4 text-xs text-muted-foreground border-t border-border pt-3">
              {Object.entries(TYPE_COLORS).map(([type, color]) => (
                <span key={type} className="flex items-center gap-1">
                  <span
                    className="inline-block w-3 h-3 rounded"
                    style={{ background: color }}
                  />
                  {TYPE_LABELS[type] || type}
                </span>
              ))}
              <span className="text-muted-foreground/50">|</span>
              {['p95', 'p90', 'p80', 'p50'].map((level) => (
                <span key={level} className="flex items-center gap-1">
                  <span
                    className="inline-block w-3 rounded"
                    style={{
                      height: `${BAR_HEIGHTS[level] / 3}px`,
                      background: '#666',
                      opacity: LEVEL_OPACITY[level],
                    }}
                  />
                  {LEVEL_LABELS[level]}
                </span>
              ))}
              <span className="text-muted-foreground/50">|</span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-0.5" style={{ background: '#4CAF50', borderTop: '1.5px dashed #4CAF50' }} />
                Target (on-time)
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-0.5" style={{ background: '#D32F2F', borderTop: '1.5px dashed #D32F2F' }} />
                Target (at risk)
              </span>
            </div>
          </>
        )}

        {/* Tooltip */}
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
            maxWidth: '320px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          }}
        />
      </CardContent>
    </Card>
  );
};

ConfidenceFunnel.propTypes = {
  configId: PropTypes.number.isRequired,
  productId: PropTypes.string.isRequired,
  siteId: PropTypes.number.isRequired,
  horizonDays: PropTypes.number,
  onClose: PropTypes.func,
};

export default ConfidenceFunnel;
