/**
 * Allocation Conflict Dialog Component
 *
 * Phase 3: Full ATP/CTP Integration
 * Displays UI for resolving ATP allocation conflicts when multiple customers
 * request more than available ATP.
 *
 * Props:
 * - open: Boolean to control dialog visibility
 * - onClose: Callback when dialog is closed
 * - gameId: Game ID
 * - scenarioUserId: ScenarioUser ID (supplier node)
 * - customers: Array of customer demands
 * - availableATP: Available ATP to allocate
 * - onAllocationComplete: Callback with allocation result
 */

import React, { useState } from 'react';
import {
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Alert,
  Badge,
  Spinner,
} from '../common';
import { cn } from '../../lib/utils/cn';
import {
  AlertTriangle,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { api } from '../../services/api';

const AllocationConflictDialog = ({
  open,
  onClose,
  gameId,
  scenarioUserId,
  customers = [],
  availableATP = 0,
  onAllocationComplete,
}) => {
  const [allocationMethod, setAllocationMethod] = useState('proportional');
  const [previewAllocation, setPreviewAllocation] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Calculate total demand
  const totalDemand = customers.reduce((sum, c) => sum + c.demand, 0);
  const shortfall = Math.max(0, totalDemand - availableATP);

  // Handle allocation method change
  const handleMethodChange = (event) => {
    const method = event.target.value;
    setAllocationMethod(method);

    // Calculate preview based on method
    calculatePreview(method);
  };

  // Calculate allocation preview
  const calculatePreview = (method) => {
    let allocations = [];

    if (totalDemand <= availableATP) {
      // Sufficient ATP - fulfill all
      allocations = customers.map(c => ({
        ...c,
        allocated: c.demand,
        unmet: 0,
        fillRate: 1.0,
      }));
    } else {
      // Conflict - need allocation logic
      if (method === 'priority') {
        // Sort by priority (1=high first)
        const sorted = [...customers].sort((a, b) => a.priority - b.priority);
        let remaining = availableATP;

        allocations = sorted.map(c => {
          const allocated = Math.min(c.demand, remaining);
          remaining -= allocated;
          return {
            ...c,
            allocated,
            unmet: c.demand - allocated,
            fillRate: c.demand > 0 ? allocated / c.demand : 1.0,
          };
        });
      } else if (method === 'fcfs') {
        // First-come-first-served
        let remaining = availableATP;

        allocations = customers.map(c => {
          const allocated = Math.min(c.demand, remaining);
          remaining -= allocated;
          return {
            ...c,
            allocated,
            unmet: c.demand - allocated,
            fillRate: c.demand > 0 ? allocated / c.demand : 1.0,
          };
        });
      } else {
        // Proportional (default)
        allocations = customers.map(c => {
          const ratio = totalDemand > 0 ? c.demand / totalDemand : 0;
          const allocated = Math.floor(availableATP * ratio);
          return {
            ...c,
            allocated,
            unmet: c.demand - allocated,
            fillRate: c.demand > 0 ? allocated / c.demand : 1.0,
          };
        });
      }
    }

    setPreviewAllocation(allocations);
  };

  // Initial preview calculation
  React.useEffect(() => {
    if (open && customers.length > 0) {
      calculatePreview(allocationMethod);
    }
  }, [open, customers, availableATP, allocationMethod]);

  // Handle allocation confirmation
  const handleConfirmAllocation = async () => {
    setSubmitting(true);
    setError(null);

    try {
      const response = await api.post(`/mixed-scenarios/${gameId}/allocate-atp`, {
        scenario_user_id: scenarioUserId,
        demands: customers.map(c => ({
          customer_id: c.customer_id,
          customer_name: c.customer_name,
          demand: c.demand,
          priority: c.priority || 2,
        })),
        allocation_method: allocationMethod,
      });

      const allocationResult = response.data;

      // Call completion callback
      if (onAllocationComplete) {
        onAllocationComplete(allocationResult);
      }

      // Close dialog
      onClose();
    } catch (err) {
      console.error('Allocation error:', err);
      setError(err.response?.data?.detail || 'Failed to allocate ATP');
    } finally {
      setSubmitting(false);
    }
  };

  const getPriorityLabel = (priority) => {
    switch (priority) {
      case 1:
        return 'High';
      case 2:
        return 'Medium';
      case 3:
        return 'Low';
      default:
        return 'Unknown';
    }
  };

  const getPriorityVariant = (priority) => {
    switch (priority) {
      case 1:
        return 'destructive';
      case 2:
        return 'warning';
      case 3:
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  return (
    <Modal isOpen={open} onClose={onClose} size="lg">
      <ModalHeader>
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-6 w-6 text-warning" />
          <ModalTitle>Allocation Conflict Resolution</ModalTitle>
        </div>
      </ModalHeader>

      <ModalBody>
        <div className="flex flex-col gap-6">
          {/* Conflict Summary */}
          <div>
            <div className="flex items-center gap-6">
              <div>
                <span className="text-xs text-muted-foreground block">
                  Total Demand
                </span>
                <span className="text-2xl font-semibold text-destructive">
                  {totalDemand} units
                </span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">
                  Available ATP
                </span>
                <span className="text-2xl font-semibold text-primary">
                  {availableATP} units
                </span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">
                  Shortfall
                </span>
                <span className="text-2xl font-semibold text-warning">
                  {shortfall} units
                </span>
              </div>
            </div>
          </div>

          <hr className="border-border" />

          {/* Customer Demands */}
          <div>
            <h4 className="text-sm font-medium mb-2">
              Customer Requests
            </h4>
            <TableContainer>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Customer</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead className="text-right">Demand</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {customers.map((customer) => (
                    <TableRow key={customer.customer_id}>
                      <TableCell>
                        <strong>{customer.customer_name}</strong>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={getPriorityVariant(customer.priority)}
                          size="sm"
                        >
                          {getPriorityLabel(customer.priority)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <strong>{customer.demand}</strong> units
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </div>

          <hr className="border-border" />

          {/* Allocation Strategy Selection */}
          <div>
            <fieldset>
              <legend className="text-sm font-medium text-foreground mb-3">
                Select Allocation Strategy
              </legend>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="allocationMethod"
                    value="proportional"
                    checked={allocationMethod === 'proportional'}
                    onChange={handleMethodChange}
                    className="mt-1 h-4 w-4 text-primary border-input focus:ring-primary"
                  />
                  <div>
                    <span className="text-sm font-medium">
                      Proportional <span className="text-muted-foreground">(Recommended)</span>
                    </span>
                    <span className="text-xs text-muted-foreground block">
                      Split ATP proportionally based on demand ratios (fair to all)
                    </span>
                  </div>
                </label>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="allocationMethod"
                    value="priority"
                    checked={allocationMethod === 'priority'}
                    onChange={handleMethodChange}
                    className="mt-1 h-4 w-4 text-primary border-input focus:ring-primary"
                  />
                  <div>
                    <span className="text-sm font-medium">
                      Priority-Based
                    </span>
                    <span className="text-xs text-muted-foreground block">
                      High-priority customers fulfilled first (may leave others short)
                    </span>
                  </div>
                </label>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="allocationMethod"
                    value="fcfs"
                    checked={allocationMethod === 'fcfs'}
                    onChange={handleMethodChange}
                    className="mt-1 h-4 w-4 text-primary border-input focus:ring-primary"
                  />
                  <div>
                    <span className="text-sm font-medium">
                      First-Come-First-Served
                    </span>
                    <span className="text-xs text-muted-foreground block">
                      Fulfill requests in order received (simple but may cause inequity)
                    </span>
                  </div>
                </label>
              </div>
            </fieldset>
          </div>

          <hr className="border-border" />

          {/* Allocation Preview */}
          {previewAllocation && (
            <div>
              <h4 className="text-sm font-medium mb-2">
                Allocation Preview ({allocationMethod})
              </h4>
              <TableContainer>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Customer</TableHead>
                      <TableHead className="text-right">Demand</TableHead>
                      <TableHead className="text-right">Allocated</TableHead>
                      <TableHead className="text-right">Unmet</TableHead>
                      <TableHead className="text-right">Fill Rate</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewAllocation.map((alloc) => (
                      <TableRow key={alloc.customer_id}>
                        <TableCell>
                          <strong>{alloc.customer_name}</strong>
                        </TableCell>
                        <TableCell className="text-right">{alloc.demand} units</TableCell>
                        <TableCell className="text-right">
                          <span
                            className={cn(
                              'text-sm font-semibold',
                              alloc.allocated === alloc.demand
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-warning'
                            )}
                          >
                            {alloc.allocated} units
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          <span
                            className={cn(
                              'text-sm',
                              alloc.unmet > 0
                                ? 'text-destructive'
                                : 'text-muted-foreground'
                            )}
                          >
                            {alloc.unmet} units
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge
                            variant={
                              alloc.fillRate >= 0.95
                                ? 'success'
                                : alloc.fillRate >= 0.7
                                ? 'warning'
                                : 'destructive'
                            }
                            size="sm"
                          >
                            {(alloc.fillRate * 100).toFixed(0)}%
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Business Impact Summary */}
              <div className="mt-3 p-3 bg-muted/50 rounded-md">
                <span className="text-xs text-muted-foreground font-medium block mb-1">
                  Business Impact:
                </span>
                <span className="text-xs text-foreground block">
                  * {previewAllocation.filter(a => a.fillRate >= 0.95).length} customer(s) fully satisfied (&gt;=95% fill rate)
                </span>
                <span className="text-xs text-foreground block">
                  * {previewAllocation.filter(a => a.fillRate >= 0.7 && a.fillRate < 0.95).length} customer(s) partially satisfied (70-95% fill rate)
                </span>
                <span className="text-xs text-foreground block">
                  * {previewAllocation.filter(a => a.fillRate < 0.7).length} customer(s) severely impacted (&lt;70% fill rate)
                </span>
              </div>
            </div>
          )}

          {/* Error message */}
          {error && (
            <Alert variant="error" icon={AlertTriangle}>
              {error}
            </Alert>
          )}
        </div>
      </ModalBody>

      <ModalFooter>
        <Button variant="outline" onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          onClick={handleConfirmAllocation}
          disabled={submitting}
          leftIcon={submitting ? <Spinner size="sm" /> : <CheckCircle2 className="h-4 w-4" />}
        >
          {submitting ? 'Allocating...' : 'Confirm Allocation'}
        </Button>
      </ModalFooter>
    </Modal>
  );
};

export default AllocationConflictDialog;
