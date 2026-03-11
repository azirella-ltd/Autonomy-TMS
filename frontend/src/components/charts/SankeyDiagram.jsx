import React, { useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import {
  sankey,
  sankeyJustify,
  sankeyCenter,
  sankeyLeft,
  sankeyRight,
  sankeyLinkHorizontal,
} from 'd3-sankey';
import { cn } from '../../lib/utils/cn';

const ALIGN_FUNCTIONS = {
  justify: sankeyJustify,
  center: sankeyCenter,
  left: sankeyLeft,
  right: sankeyRight,
};

const MIN_LINK_VALUE = 1e-6;
const NODE_LABEL_FONT_SIZE = 12; // px
const NODE_LABEL_LINE_HEIGHT = 1.5;
const MIN_SCALE_RATIO = 0.05;

// Default colors (matching previous MUI theme palette)
const DEFAULT_PRIMARY_COLOR = '#3b82f6'; // primary.main
const DEFAULT_PRIMARY_LIGHT = '#60a5fa'; // primary.light
const DEFAULT_TEXT_PRIMARY = '#1e293b'; // text.primary
const DEFAULT_TEXT_SECONDARY = '#64748b'; // text.secondary
const DEFAULT_GREY_500 = '#6b7280'; // grey[500]
const DEFAULT_GREY_700 = '#374151'; // grey[700]

const normalizeId = (value, fallback) => {
  if (value === undefined || value === null) {
    return String(fallback);
  }
  return String(value);
};

const normalizeType = (value) => String(value ?? '').toLowerCase();

// Simple Tooltip component for SVG elements
const SvgTooltip = ({ children, content, placement = 'top' }) => {
  const [show, setShow] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const tooltipRef = useRef(null);

  const handleMouseEnter = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setPosition({
      x: rect.left + rect.width / 2,
      y: rect.top,
    });
    setShow(true);
  };

  const handleMouseLeave = () => {
    setShow(false);
  };

  const handleMouseMove = (e) => {
    setPosition({
      x: e.clientX,
      y: e.clientY - 10,
    });
  };

  return (
    <g
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseMove={handleMouseMove}
    >
      {children}
      {show && content && (
        <foreignObject
          x={position.x - 100}
          y={position.y - 40}
          width={200}
          height={100}
          style={{ overflow: 'visible', pointerEvents: 'none' }}
        >
          <div
            ref={tooltipRef}
            className="bg-popover text-popover-foreground text-xs px-2 py-1 rounded shadow-lg border border-border whitespace-nowrap"
            style={{
              position: 'fixed',
              left: position.x,
              top: position.y - 30,
              transform: 'translateX(-50%)',
              zIndex: 50,
            }}
          >
            {content}
          </div>
        </foreignObject>
      )}
    </g>
  );
};

const SankeyDiagram = ({
  nodes,
  links,
  height = 360,
  margin = { top: 16, right: 120, bottom: 16, left: 120 },
  nodeWidth = 18,
  nodePadding = 48,
  align = 'justify',
  minLinkBreadth = MIN_LINK_VALUE,
  defaultLinkOpacity = 0.6,
  defaultLinkColor,
  linkColorAccessor,
  linkTooltip,
  nodeTooltip,
  renderNodeTopLabel,
  renderNodeBottomLabel,
  nodeCornerRadius = 0,
  showNodes = true,
  showLinks = true,
  emptyState = null,
  renderDecorators,
  columnOrder,
  nodeSort,
}) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [tooltipContent, setTooltipContent] = useState(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });

  const fallbackWidth = useMemo(() => {
    const nodeCount = Array.isArray(nodes) ? nodes.length : 0;
    const base = nodeCount > 0 ? nodeCount * (nodeWidth + nodePadding) : 360;
    return Math.max(base + margin.left + margin.right, 480);
  }, [margin.left, margin.right, nodePadding, nodeWidth, nodes]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return undefined;
    }

    const updateWidth = () => {
      const rect = element.getBoundingClientRect();
      const measured = Number.isFinite(rect?.width) ? rect.width : element.offsetWidth ?? 0;
      const applied = measured > 8 ? measured : fallbackWidth;
      setContainerWidth((prev) => (prev !== applied ? applied : prev));
    };

    updateWidth();

    const raf = window.requestAnimationFrame(updateWidth);
    const timeoutId = window.setTimeout(updateWidth, 120);

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(updateWidth);
      observer.observe(element);
      return () => {
        observer.disconnect();
        window.cancelAnimationFrame(raf);
        window.clearTimeout(timeoutId);
      };
    }

    window.addEventListener('resize', updateWidth);
    return () => {
      window.removeEventListener('resize', updateWidth);
      window.cancelAnimationFrame(raf);
      window.clearTimeout(timeoutId);
    };
  }, [fallbackWidth]);

  const columnIndexMap = useMemo(() => {
    if (!Array.isArray(columnOrder) || columnOrder.length === 0) {
      return null;
    }
    const map = new Map();
    columnOrder.forEach((token, index) => {
      map.set(normalizeType(token), index);
    });
    return map;
  }, [columnOrder]);

  const alignFunction = useMemo(() => {
    if (columnIndexMap) {
      return (node, n) => {
        const typeToken = normalizeType(node.type ?? node.role ?? node.name);
        const columnIdx = columnIndexMap.get(typeToken);
        if (columnIdx === undefined) {
          return Math.min(n - 1, Math.max(0, Math.round(n / 2)));
        }
        return Math.min(n - 1, Math.max(0, columnIdx));
      };
    }
    return ALIGN_FUNCTIONS[align] ?? sankeyJustify;
  }, [align, columnIndexMap]);

  const layout = useMemo(() => {
    if (!nodes?.length || !links?.length) {
      return null;
    }

    const availableWidth = containerWidth || fallbackWidth;
    if (!availableWidth) {
      return null;
    }

    const innerWidth = Math.max(availableWidth - (margin.left + margin.right), 1);
    const innerHeight = Math.max(height - (margin.top + margin.bottom), 1);
    if (!innerWidth || !innerHeight) {
      return null;
    }

    const layerCounts = new Map();
    (Array.isArray(nodes) ? nodes : []).forEach((node) => {
      const typeToken = normalizeType(node.type ?? node.role ?? node.name);
      const columnIdx = columnIndexMap ? columnIndexMap.get(typeToken) ?? -1 : 0;
      layerCounts.set(columnIdx, (layerCounts.get(columnIdx) ?? 0) + 1);
    });
    const nodeCount = Array.isArray(nodes) ? nodes.length : 0;
    const maxLayerCount =
      layerCounts.size > 0
        ? Math.max(...Array.from(layerCounts.values()))
        : nodeCount;
    const reservedHeight =
      maxLayerCount > 0
        ? maxLayerCount * NODE_LABEL_FONT_SIZE * NODE_LABEL_LINE_HEIGHT
        : NODE_LABEL_FONT_SIZE * NODE_LABEL_LINE_HEIGHT;
    const usableHeight = Math.max(innerHeight - reservedHeight, innerHeight * MIN_SCALE_RATIO);
    const nodeScaleRatio = Math.max(MIN_SCALE_RATIO, Math.min(usableHeight / innerHeight, 1));

    const nodeInputs = [];
    const nodeIndexById = new Map();
    (Array.isArray(nodes) ? nodes : []).forEach((node, index) => {
      const id = normalizeId(node?.id ?? node?.key ?? node?.name, index);
      if (!id || nodeIndexById.has(id)) {
        return;
      }
      const shipmentsRaw = Number(node.shipments ?? node.value ?? node.capacityValue ?? 1);
      const shipments = Number.isFinite(shipmentsRaw)
        ? Math.max(MIN_LINK_VALUE, Math.abs(shipmentsRaw))
        : MIN_LINK_VALUE;
      const scaledShipments = shipments * nodeScaleRatio;
      const normalized = {
        ...node,
        id,
        color: node.color ?? DEFAULT_PRIMARY_COLOR,
        shipments: scaledShipments,
        type: normalizeType(node.type ?? node.role ?? node.name ?? index),
      };
      nodeIndexById.set(id, nodeInputs.length);
      nodeInputs.push(normalized);
    });

    if (!nodeInputs.length) {
      return null;
    }

    const linkInputs = [];
    (Array.isArray(links) ? links : []).forEach((link, index) => {
      const sourceId = normalizeId(
        typeof link.source === 'object'
          ? link.source.id ?? link.source.key ?? link.source.name
          : link.source,
        link.source ?? `source-${index}`
      );
      const targetId = normalizeId(
        typeof link.target === 'object'
          ? link.target.id ?? link.target.key ?? link.target.name
          : link.target,
        link.target ?? `target-${index}`
      );
      const sourceIndex = nodeIndexById.get(sourceId);
      const targetIndex = nodeIndexById.get(targetId);
      if (sourceIndex === undefined || targetIndex === undefined) {
        return;
      }
      const rawValue = Number(link.value);
      const baseValue = Number.isFinite(rawValue) && rawValue > 0 ? rawValue : minLinkBreadth;
      const value = Math.max(baseValue * nodeScaleRatio, minLinkBreadth * nodeScaleRatio);
      const color =
        link.color ??
        (typeof link.source === 'object' && link.source.color) ??
        (typeof link.target === 'object' && link.target.color) ??
        undefined;
      linkInputs.push({
        ...link,
        source: sourceIndex,
        target: targetIndex,
        value,
        color,
      });
    });

    if (!linkInputs.length) {
      return null;
    }

    const generator = sankey()
      .nodeId((d) => d.index)
      .nodeAlign(alignFunction)
      .nodeWidth(nodeWidth)
      .nodePadding(nodePadding)
      .extent([
        [0, 0],
        [innerWidth, innerHeight],
      ])
      .nodeSort(nodeSort || null)
      .linkSort(null);

    try {
      // Build clean copies, stripping any stale d3-sankey properties from prior runs
      const cleanNodes = nodeInputs.map((node, i) => {
        const { sourceLinks, targetLinks, depth, height, layer, x0, x1, y0, y1, index, ...rest } = node;
        return { ...rest, index: i };
      });
      const cleanLinks = linkInputs.map((link) => {
        const { index, width, y0, y1, ...rest } = link;
        return { ...rest };
      });
      const sankeyData = generator({
        nodes: cleanNodes,
        links: cleanLinks,
      });

      if (columnIndexMap && columnIndexMap.size > 0) {
        const maxColumnIndex = Math.max(...columnIndexMap.values());
        const widthSpan = Math.max(innerWidth - nodeWidth, 1);
        const columnSpacing = maxColumnIndex > 0 ? widthSpan / maxColumnIndex : 0;

        const resolveColumnPosition = (node) => {
          const columnIdx = columnIndexMap.get(normalizeType(node.type ?? node.role ?? node.name));
          if (columnIdx === undefined) {
            return null;
          }
          return Math.max(0, Math.min(maxColumnIndex, columnIdx));
        };

        sankeyData.nodes.forEach((node) => {
          const columnPosition = resolveColumnPosition(node);
          if (columnPosition === null) {
            return;
          }
          const x0 = columnPosition * columnSpacing;
          node.x0 = x0;
          node.x1 = x0 + nodeWidth;
          node.depth = columnPosition;
        });
      }

      // --- Crossing minimization (barycenter heuristic) ---
      // Group nodes by column, then reorder each column so that nodes
      // appear in the same vertical order as the average y-center of
      // their connected neighbors. This dramatically reduces crossings.
      const columnGroups = new Map();
      sankeyData.nodes.forEach((node) => {
        const col = node.depth ?? 0;
        if (!columnGroups.has(col)) columnGroups.set(col, []);
        columnGroups.get(col).push(node);
      });

      const getNeighborBarycenter = (node) => {
        const neighbors = [];
        if (node.sourceLinks) {
          node.sourceLinks.forEach((link) => {
            const target = link.target;
            if (target && typeof target === 'object') {
              neighbors.push((target.y0 + target.y1) / 2);
            }
          });
        }
        if (node.targetLinks) {
          node.targetLinks.forEach((link) => {
            const source = link.source;
            if (source && typeof source === 'object') {
              neighbors.push((source.y0 + source.y1) / 2);
            }
          });
        }
        if (neighbors.length === 0) return (node.y0 + node.y1) / 2;
        return neighbors.reduce((sum, v) => sum + v, 0) / neighbors.length;
      };

      // Run 4 sweeps (forward and backward) for convergence
      const sortedColumns = Array.from(columnGroups.keys()).sort((a, b) => a - b);
      for (let sweep = 0; sweep < 4; sweep++) {
        const cols = sweep % 2 === 0 ? sortedColumns : [...sortedColumns].reverse();
        for (const col of cols) {
          const nodesInCol = columnGroups.get(col);
          if (!nodesInCol || nodesInCol.length <= 1) continue;

          // Compute barycenter for each node
          const scored = nodesInCol.map((node) => ({
            node,
            barycenter: getNeighborBarycenter(node),
          }));
          scored.sort((a, b) => a.barycenter - b.barycenter);

          // Reassign y positions preserving node heights and padding
          let currentY = Math.min(...nodesInCol.map((n) => n.y0));
          scored.forEach(({ node }) => {
            const nodeHeight = node.y1 - node.y0;
            node.y0 = currentY;
            node.y1 = currentY + nodeHeight;
            currentY += nodeHeight + nodePadding;
          });
        }
      }

      // Recompute link y positions after reordering
      sankeyData.nodes.forEach((node) => {
        if (!node.sourceLinks || !node.targetLinks) return;
        // Sort source links (outgoing) by target y position
        node.sourceLinks.sort((a, b) => {
          const ay = typeof a.target === 'object' ? a.target.y0 : 0;
          const by = typeof b.target === 'object' ? b.target.y0 : 0;
          return ay - by;
        });
        let y0 = node.y0;
        node.sourceLinks.forEach((link) => {
          link.y0 = y0 + (link.width || 0) / 2;
          y0 += link.width || 0;
        });
        // Sort target links (incoming) by source y position
        node.targetLinks.sort((a, b) => {
          const ay = typeof a.source === 'object' ? a.source.y0 : 0;
          const by = typeof b.source === 'object' ? b.source.y0 : 0;
          return ay - by;
        });
        let y1 = node.y0;
        node.targetLinks.forEach((link) => {
          link.y1 = y1 + (link.width || 0) / 2;
          y1 += link.width || 0;
        });
      });

      const resolveNodeId = (ref) => {
        if (ref && typeof ref === 'object' && ref !== null) {
          if (typeof ref.index === 'number' && nodeInputs[ref.index]) {
            return nodeInputs[ref.index].id;
          }
          if (ref.id !== undefined && ref.id !== null) {
            return normalizeId(ref.id, ref.id);
          }
        }
        if (ref !== undefined && ref !== null && nodeInputs[ref]) {
          return nodeInputs[ref].id;
        }
        if (ref === undefined || ref === null) {
          return undefined;
        }
        return normalizeId(ref, ref);
      };

      // Determine min/max depth (column) for side-label positioning
      const depths = sankeyData.nodes.map((n) => n.depth ?? 0);
      const minDepth = Math.min(...depths);
      const maxDepth = Math.max(...depths);

      const inferNodeSide = (node) => {
        const depth = node.depth ?? 0;
        if (depth <= minDepth) return 'left';
        if (depth >= maxDepth) return 'right';
        return 'right'; // middle columns: label to the right (standard Sankey convention)
      };

      const nodesWithMeta = sankeyData.nodes.map((node, idx) => ({
        ...node,
        id: nodeInputs[idx]?.id ?? node.id ?? idx,
        type: nodeInputs[idx]?.type ?? node.type,
        color: nodeInputs[idx]?.color ?? node.color,
        side: inferNodeSide(node),
      }));

      const linksWithMeta = sankeyData.links.map((link, idx) => ({
        ...link,
        sourceId: resolveNodeId(link.source),
        targetId: resolveNodeId(link.target),
        color:
          linkInputs[idx]?.color ??
          link.color ??
          (typeof link.source === 'object' ? link.source.color : undefined) ??
          (typeof link.target === 'object' ? link.target.color : undefined),
      }));

      return {
        width: availableWidth,
        height,
        nodes: nodesWithMeta,
        links: linksWithMeta,
      };
    } catch (error) {
      console.error('Failed to generate Sankey layout', error);
      return null;
    }
  }, [
    alignFunction,
    columnIndexMap,
    containerWidth,
    fallbackWidth,
    height,
    links,
    margin.bottom,
    margin.left,
    margin.right,
    margin.top,
    minLinkBreadth,
    nodePadding,
    nodeWidth,
    nodes,
    nodeSort,
  ]);

  const defaultLinkStroke = defaultLinkColor ?? DEFAULT_PRIMARY_LIGHT;

  const nodeTopLabelRenderer =
    renderNodeTopLabel ?? ((node) => node.name ?? node.id ?? '');

  const nodeBottomLabelRenderer = renderNodeBottomLabel ?? (() => null);

  const normalizeBottomLabelLines = (value) => {
    if (value === null || value === undefined || value === false) {
      return [];
    }
    const lines = [];
    const appendEntry = (entry) => {
      if (entry === null || entry === undefined || entry === false) {
        return;
      }
      if (Array.isArray(entry)) {
        entry.forEach((nested) => appendEntry(nested));
        return;
      }
      if (typeof entry === 'string' || typeof entry === 'number') {
        const text = String(entry);
        const segments = text.split(/\n+/);
        segments.forEach((segment) => {
          const trimmed = segment.trim();
          if (trimmed.length > 0) {
            lines.push(trimmed);
          }
        });
        if (!segments.length) {
          lines.push(text);
        }
        return;
      }
      if (React.isValidElement(entry)) {
        lines.push(entry);
        return;
      }
      lines.push(String(entry));
    };
    appendEntry(value);
    return lines;
  };

  const linkColorGetter = linkColorAccessor ?? ((link) => link.color ?? defaultLinkStroke);

  const handleMouseMove = (e, content) => {
    if (content) {
      setTooltipContent(content);
      setTooltipPosition({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseLeave = () => {
    setTooltipContent(null);
  };

  return (
    <div
      ref={containerRef}
      className={cn('w-full min-w-0 relative')}
      style={{ height }}
    >
      {!layout && emptyState}
      {layout && (
        <>
          <svg width={layout.width} height={layout.height} role="img">
            <g transform={`translate(${margin.left}, ${margin.top})`}>
              {showLinks &&
                layout.links.map((link, idx) => {
                  const stroke = linkColorGetter(link);
                  const strokeOpacity =
                    typeof link.opacity === 'number' ? link.opacity : defaultLinkOpacity;
                  const strokeWidth = Math.max(link.width ?? link.dy ?? 1.5, 1.5);
                  const dashArray = link.strokeDasharray ?? link.dashArray;
                  const pathData = sankeyLinkHorizontal()(link);

                  // Validate path data to prevent React rendering errors
                  if (!pathData || typeof pathData !== 'string' || pathData.includes('NaN')) {
                    return null;
                  }

                  return (
                    <path
                      key={`link-${idx}`}
                      d={pathData}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={strokeWidth}
                      strokeOpacity={strokeOpacity}
                      strokeDasharray={dashArray}
                      pointerEvents={linkTooltip ? 'auto' : 'none'}
                      strokeLinecap="butt"
                      onMouseMove={(e) => linkTooltip && handleMouseMove(e, linkTooltip(link))}
                      onMouseLeave={handleMouseLeave}
                      className={linkTooltip ? 'cursor-pointer' : ''}
                    />
                  );
                })}

              {showNodes &&
                layout.nodes.map((node) => {
                  // Validate node coordinates to prevent React rendering errors
                  if (!node || isNaN(node.x0) || isNaN(node.y0) || isNaN(node.x1) || isNaN(node.y1)) {
                    return null;
                  }
                  const widthValue = Math.max(node.x1 - node.x0, 1);
                  const heightValue = Math.max(node.y1 - node.y0, 1);
                  const nodeCenterY = node.y0 + heightValue / 2;
                  const labelGap = 6; // px gap between node edge and label
                  const isLeft = node.side === 'left';
                  const isRight = node.side === 'right';
                  // Side labels: positioned beside the node, vertically centered
                  // Center labels: positioned above the node (legacy behavior)
                  const labelX = isRight
                    ? node.x1 + labelGap
                    : isLeft
                      ? node.x0 - labelGap
                      : node.x0 + widthValue / 2;
                  const labelAnchor = isRight ? 'start' : isLeft ? 'end' : 'middle';
                  const topLabel = nodeTopLabelRenderer(node);
                  const rawBottomLabel = nodeBottomLabelRenderer(node);
                  const bottomLabelLines = normalizeBottomLabelLines(rawBottomLabel);
                  const hasBottomLabel = bottomLabelLines.length > 0;
                  const fill = node.color ?? DEFAULT_GREY_500;

                  return (
                    <g
                      key={`node-${node.index ?? node.id}`}
                      onMouseMove={(e) => nodeTooltip && handleMouseMove(e, nodeTooltip(node))}
                      onMouseLeave={handleMouseLeave}
                      className={nodeTooltip ? 'cursor-pointer' : ''}
                    >
                      <rect
                        x={node.x0}
                        y={node.y0}
                        width={widthValue}
                        height={heightValue}
                        rx={nodeCornerRadius}
                        ry={nodeCornerRadius}
                        fill={fill}
                        stroke={node.strokeColor ?? DEFAULT_GREY_700}
                        strokeWidth={node.strokeWidth ?? 1}
                        opacity={node.opacity ?? 0.9}
                      />
                      {topLabel && (
                        <text
                          x={labelX}
                          y={isLeft || isRight ? nodeCenterY : node.y0 - 1}
                          textAnchor={labelAnchor}
                          dominantBaseline={isLeft || isRight ? 'central' : 'auto'}
                          fill={node.topLabelColor ?? DEFAULT_TEXT_PRIMARY}
                          fontSize={11}
                          fontWeight={500}
                        >
                          {topLabel}
                        </text>
                      )}
                      {hasBottomLabel && (
                        <text
                          x={labelX}
                          y={isLeft || isRight ? nodeCenterY + 14 : node.y1 + 14}
                          textAnchor={labelAnchor}
                          dominantBaseline={isLeft || isRight ? 'central' : 'auto'}
                          fill={node.bottomLabelColor ?? DEFAULT_TEXT_SECONDARY}
                          fontSize={10}
                        >
                          {bottomLabelLines.map((line, idx) => {
                            if (React.isValidElement(line)) {
                              return React.cloneElement(line, {
                                key: line.key ?? `node-${node.index ?? node.id}-lbl-${idx}`,
                                x: line.props?.x ?? labelX,
                                dy: line.props?.dy ?? (idx === 0 ? 0 : 13),
                              });
                            }
                            return (
                              <tspan
                                key={`node-${node.index ?? node.id}-lbl-${idx}`}
                                x={labelX}
                                dy={idx === 0 ? 0 : 13}
                              >
                                {line}
                              </tspan>
                            );
                          })}
                        </text>
                      )}
                    </g>
                  );
                })}

              {renderDecorators && renderDecorators(layout)}
            </g>
          </svg>
          {/* Tooltip */}
          {tooltipContent && (
            <div
              className="fixed bg-popover text-popover-foreground text-xs px-2 py-1 rounded shadow-lg border border-border whitespace-nowrap z-50 pointer-events-none"
              style={{
                left: tooltipPosition.x + 10,
                top: tooltipPosition.y - 10,
              }}
            >
              {tooltipContent}
            </div>
          )}
        </>
      )}
    </div>
  );
};

SankeyDiagram.propTypes = {
  nodes: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
      name: PropTypes.string,
      type: PropTypes.string,
      color: PropTypes.string,
      shipments: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
      capacityValue: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
    })
  ).isRequired,
  links: PropTypes.arrayOf(
    PropTypes.shape({
      source: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.object]),
      target: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.object]),
      value: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
      color: PropTypes.string,
    })
  ).isRequired,
  height: PropTypes.number,
  margin: PropTypes.shape({
    top: PropTypes.number,
    right: PropTypes.number,
    bottom: PropTypes.number,
    left: PropTypes.number,
  }),
  nodeWidth: PropTypes.number,
  nodePadding: PropTypes.number,
  align: PropTypes.oneOf(['justify', 'center', 'left', 'right']),
  minLinkBreadth: PropTypes.number,
  defaultLinkOpacity: PropTypes.number,
  defaultLinkColor: PropTypes.string,
  linkColorAccessor: PropTypes.func,
  linkTooltip: PropTypes.func,
  nodeTooltip: PropTypes.func,
  renderNodeTopLabel: PropTypes.func,
  renderNodeBottomLabel: PropTypes.func,
  nodeCornerRadius: PropTypes.number,
  showNodes: PropTypes.bool,
  showLinks: PropTypes.bool,
  emptyState: PropTypes.node,
  renderDecorators: PropTypes.func,
  columnOrder: PropTypes.arrayOf(PropTypes.string),
  nodeSort: PropTypes.func,
};

export default SankeyDiagram;
