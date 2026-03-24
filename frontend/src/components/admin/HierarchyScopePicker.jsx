/**
 * HierarchyScopePicker — Checkable tree for assigning site/product scope.
 *
 * Renders a hierarchy tree with checkboxes. Selecting a parent implicitly
 * includes all descendants (hierarchy inheritance). Only the highest selected
 * ancestor code is stored — the backend resolves descendants via path prefix.
 *
 * Props:
 *   nodes: [{id, code, name, level, parent_id, depth}] — flat list sorted by hierarchy_path
 *   selectedCodes: string[] — currently selected hierarchy codes
 *   onChange: (codes: string[]) => void
 *   label: string — "Site Scope" or "Product Scope"
 *   loading: boolean
 */

import React, { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, Check, Globe, Package } from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const LEVEL_COLORS = {
  COMPANY: 'text-violet-600',
  REGION: 'text-blue-600',
  COUNTRY: 'text-emerald-600',
  STATE: 'text-amber-600',
  SITE: 'text-foreground',
  CATEGORY: 'text-violet-600',
  FAMILY: 'text-blue-600',
  GROUP: 'text-emerald-600',
  PRODUCT: 'text-foreground',
};

export default function HierarchyScopePicker({
  nodes = [],
  selectedCodes = [],
  onChange,
  label = 'Scope',
  loading = false,
  icon: IconComponent,
}) {
  const [expanded, setExpanded] = useState(new Set());

  // Build tree structure from flat list
  const tree = useMemo(() => {
    const map = new Map();
    const roots = [];
    for (const node of nodes) {
      map.set(node.id, { ...node, children: [] });
    }
    for (const node of nodes) {
      const entry = map.get(node.id);
      if (node.parent_id && map.has(node.parent_id)) {
        map.get(node.parent_id).children.push(entry);
      } else {
        roots.push(entry);
      }
    }
    return roots;
  }, [nodes]);

  // Get all descendant codes for a node
  const getDescendantCodes = (node) => {
    const codes = [node.code];
    for (const child of node.children || []) {
      codes.push(...getDescendantCodes(child));
    }
    return codes;
  };

  // Get all ancestor codes for a node
  const getAncestorCodes = (nodeCode) => {
    const codes = [];
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    let current = nodes.find((n) => n.code === nodeCode);
    while (current?.parent_id) {
      const parent = nodeMap.get(current.parent_id);
      if (parent) {
        codes.push(parent.code);
        current = parent;
      } else {
        break;
      }
    }
    return codes;
  };

  // Check if a node is selected (directly or via ancestor)
  const isSelected = (code) => {
    if (selectedCodes.includes(code)) return true;
    // Check if any ancestor is selected (implicit inclusion)
    const ancestors = getAncestorCodes(code);
    return ancestors.some((a) => selectedCodes.includes(a));
  };

  // Check if node is implicitly selected via ancestor
  const isImplicit = (code) => {
    if (selectedCodes.includes(code)) return false;
    const ancestors = getAncestorCodes(code);
    return ancestors.some((a) => selectedCodes.includes(a));
  };

  const handleToggle = (code) => {
    const selected = new Set(selectedCodes);

    if (isSelected(code)) {
      // Uncheck: remove this code and any descendant codes
      const node = nodes.find((n) => n.code === code);
      if (node) {
        const nodeEntry = buildNodeMap().get(node.id);
        if (nodeEntry) {
          const descendants = getDescendantCodes(nodeEntry);
          descendants.forEach((c) => selected.delete(c));
        }
      }
      selected.delete(code);

      // If an ancestor was selected, we need to remove it and add siblings
      // For simplicity, just remove the ancestor too — user can re-select what they want
      const ancestors = getAncestorCodes(code);
      ancestors.forEach((a) => selected.delete(a));
    } else {
      // Check: add this code, remove any descendant codes (parent subsumes children)
      const node = nodes.find((n) => n.code === code);
      if (node) {
        const nodeEntry = buildNodeMap().get(node.id);
        if (nodeEntry) {
          const descendants = getDescendantCodes(nodeEntry);
          descendants.forEach((c) => selected.delete(c));
        }
      }
      selected.add(code);
    }

    onChange([...selected]);
  };

  const buildNodeMap = () => {
    const map = new Map();
    for (const node of nodes) {
      map.set(node.id, { ...node, children: [] });
    }
    for (const node of nodes) {
      const entry = map.get(node.id);
      if (node.parent_id && map.has(node.parent_id)) {
        map.get(node.parent_id).children.push(entry);
      }
    }
    return map;
  };

  const toggleExpand = (id) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Expand all on mount if small tree
  React.useEffect(() => {
    if (nodes.length > 0 && nodes.length < 50) {
      setExpanded(new Set(nodes.filter((n) => n.children?.length || nodes.some((c) => c.parent_id === n.id)).map((n) => n.id)));
    }
  }, [nodes]);

  const renderNode = (node, depth = 0) => {
    const hasChildren = node.children && node.children.length > 0;
    const isExp = expanded.has(node.id);
    const checked = isSelected(node.code);
    const implicit = isImplicit(node.code);

    return (
      <div key={node.id}>
        <div
          className={cn(
            'flex items-center gap-1.5 py-1 px-1 rounded-sm hover:bg-muted/50 cursor-pointer',
            checked && !implicit && 'bg-primary/5',
          )}
          style={{ paddingLeft: `${depth * 20 + 4}px` }}
        >
          {/* Expand/collapse */}
          {hasChildren ? (
            <button
              onClick={(e) => { e.stopPropagation(); toggleExpand(node.id); }}
              className="p-0.5 hover:bg-muted rounded"
            >
              {isExp ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </button>
          ) : (
            <span className="w-5" />
          )}

          {/* Checkbox */}
          <button
            onClick={() => handleToggle(node.code)}
            className={cn(
              'flex items-center justify-center h-4 w-4 rounded border shrink-0',
              checked
                ? implicit
                  ? 'bg-primary/30 border-primary/50'
                  : 'bg-primary border-primary'
                : 'border-muted-foreground/30 hover:border-primary',
            )}
          >
            {checked && <Check className="h-3 w-3 text-white" />}
          </button>

          {/* Label */}
          <span
            onClick={() => handleToggle(node.code)}
            className={cn('text-xs flex-1', LEVEL_COLORS[node.level] || 'text-foreground')}
          >
            {node.name}
          </span>

          {/* Level badge */}
          <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">
            {node.level?.toLowerCase()}
          </span>
        </div>

        {/* Children */}
        {hasChildren && isExp && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  const Icon = IconComponent || (label.toLowerCase().includes('site') ? Globe : Package);
  const isFullAccess = !selectedCodes || selectedCodes.length === 0;

  return (
    <div className="border rounded-lg">
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">{label}</span>
          {isFullAccess ? (
            <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-500/10 text-emerald-700">
              Full Access
            </span>
          ) : (
            <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-500/10 text-blue-700">
              {selectedCodes.length} selected
            </span>
          )}
        </div>
        {!isFullAccess && (
          <button
            onClick={() => onChange([])}
            className="text-[10px] text-muted-foreground hover:text-foreground"
          >
            Clear (Full Access)
          </button>
        )}
      </div>

      <div className="max-h-48 overflow-y-auto p-1">
        {loading ? (
          <div className="text-xs text-muted-foreground text-center py-4">Loading hierarchy...</div>
        ) : nodes.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-4">No hierarchy data available</div>
        ) : (
          tree.map((root) => renderNode(root, 0))
        )}
      </div>
    </div>
  );
}
