/**
 * Pipeline Visibility Component
 *
 * Displays in-transit shipments with timeline visualization.
 * Shows incoming orders with arrival estimates.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - shipments: Array of in-transit shipments [{quantity, origin, arrival_round, order_round, to_number}]
 * - currentRound: Current round number
 * - maxShipments: Maximum shipments to display before collapsing (default: 5)
 * - compact: Show compact view (default: false)
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Alert,
  AlertDescription,
  Progress,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  TableContainer,
  Button,
} from '../common';
import {
  Truck as ShipIcon,
  Clock as ScheduleIcon,
  ChevronDown as ExpandMoreIcon,
  ChevronUp as ExpandLessIcon,
  Info as InfoIcon,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';

const PipelineVisibility = ({
  shipments = [],
  currentRound = 1,
  maxShipments = 5,
  compact = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  // Sort shipments by arrival round (nearest first)
  const sortedShipments = [...shipments].sort((a, b) => {
    const aArrival = a.arrival_round || 999;
    const bArrival = b.arrival_round || 999;
    return aArrival - bArrival;
  });

  // Calculate total pipeline quantity
  const totalPipeline = shipments.reduce((sum, s) => sum + (s.quantity || 0), 0);

  // Calculate rounds until arrival for each shipment
  const shipmentsWithETA = sortedShipments.map(shipment => ({
    ...shipment,
    roundsUntilArrival: shipment.arrival_round
      ? Math.max(0, shipment.arrival_round - currentRound)
      : null,
  }));

  // Group shipments arriving in different time windows
  const arriving = {
    thisRound: shipmentsWithETA.filter(s => s.roundsUntilArrival === 0),
    nextRound: shipmentsWithETA.filter(s => s.roundsUntilArrival === 1),
    soon: shipmentsWithETA.filter(s => s.roundsUntilArrival >= 2 && s.roundsUntilArrival <= 3),
    later: shipmentsWithETA.filter(s => s.roundsUntilArrival > 3),
  };

  // Calculate progress percentage (how far along is the shipment)
  const calculateProgress = (orderRound, arrivalRound) => {
    if (!orderRound || !arrivalRound) return 50;
    const totalTime = arrivalRound - orderRound;
    const elapsed = currentRound - orderRound;
    return Math.min(100, Math.max(0, (elapsed / totalTime) * 100));
  };

  // Render timeline visualization for a single shipment
  const renderShipmentTimeline = (shipment, index) => {
    const progress = calculateProgress(shipment.order_round, shipment.arrival_round);
    const roundsUntil = shipment.roundsUntilArrival;
    const isArriving = roundsUntil === 0;

    return (
      <div key={index} className="mb-3">
        <div className="flex items-center gap-4">
          {/* Origin */}
          <div className="min-w-[80px]">
            <span className="text-xs text-muted-foreground">
              {shipment.origin || 'Upstream'}
            </span>
          </div>

          {/* Timeline Progress Bar */}
          <div className="flex-1 relative">
            <Progress
              value={progress}
              className={cn(
                'h-2',
                isArriving && '[&>div]:bg-emerald-500'
              )}
            />
            {/* Truck Icon on Progress */}
            <ShipIcon
              className={cn(
                'absolute -top-2 h-6 w-6 transition-all',
                isArriving ? 'text-emerald-500' : 'text-primary'
              )}
              style={{ left: `calc(${progress}% - 12px)` }}
            />
          </div>

          {/* Quantity and ETA */}
          <div className="flex items-center gap-2 min-w-[140px]">
            <Badge variant="outline" size="sm">
              {shipment.quantity} units
            </Badge>
            {roundsUntil !== null && (
              <Badge
                variant={isArriving ? 'success' : roundsUntil === 1 ? 'warning' : 'secondary'}
                size="sm"
                title={`Arrives Round ${shipment.arrival_round}`}
                className="gap-1"
              >
                <ScheduleIcon className="h-3 w-3" />
                {isArriving ? 'Now!' : `${roundsUntil}R`}
              </Badge>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Compact view - just show summary
  if (compact) {
    return (
      <div className="flex items-center gap-4">
        <ShipIcon className="h-4 w-4 text-primary" />
        <span className="text-sm">
          <strong>{totalPipeline}</strong> units in transit
        </span>
        {arriving.thisRound.length > 0 && (
          <Badge variant="success" size="sm">
            {arriving.thisRound.reduce((s, sh) => s + sh.quantity, 0)} arriving now
          </Badge>
        )}
        {arriving.nextRound.length > 0 && (
          <Badge variant="warning" size="sm">
            {arriving.nextRound.reduce((s, sh) => s + sh.quantity, 0)} next round
          </Badge>
        )}
      </div>
    );
  }

  // No shipments
  if (shipments.length === 0) {
    return (
      <Alert variant="info">
        <InfoIcon className="h-4 w-4" />
        <AlertDescription>
          No shipments currently in transit. Orders placed will appear here.
        </AlertDescription>
      </Alert>
    );
  }

  // Full view
  const visibleShipments = expanded ? shipmentsWithETA : shipmentsWithETA.slice(0, maxShipments);
  const hasMore = shipmentsWithETA.length > maxShipments;

  return (
    <Card className="border">
      <CardContent className="pt-4 pb-2">
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <ShipIcon className="h-5 w-5 text-primary" />
            <h4 className="font-semibold">Pipeline Visibility</h4>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline" size="sm">
              {shipments.length} shipments
            </Badge>
            <Badge variant="default" size="sm">
              {totalPipeline} total units
            </Badge>
          </div>
        </div>

        {/* Arrival Summary */}
        <div className="flex flex-wrap gap-2 mb-4">
          {arriving.thisRound.length > 0 && (
            <Badge variant="success" size="sm" className="gap-1">
              <ShipIcon className="h-3 w-3" />
              {arriving.thisRound.reduce((s, sh) => s + sh.quantity, 0)} arriving this round
            </Badge>
          )}
          {arriving.nextRound.length > 0 && (
            <Badge variant="warning" size="sm" className="gap-1">
              <ScheduleIcon className="h-3 w-3" />
              {arriving.nextRound.reduce((s, sh) => s + sh.quantity, 0)} next round
            </Badge>
          )}
          {arriving.soon.length > 0 && (
            <Badge variant="secondary" size="sm" className="gap-1">
              <ScheduleIcon className="h-3 w-3" />
              {arriving.soon.reduce((s, sh) => s + sh.quantity, 0)} in 2-3 periods
            </Badge>
          )}
        </div>

        {/* Shipment Timelines */}
        <div className="space-y-1">
          {visibleShipments.map((shipment, idx) => renderShipmentTimeline(shipment, idx))}
        </div>

        {/* Expand/Collapse */}
        {hasMore && (
          <div className="text-center mt-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="gap-1"
            >
              {expanded ? (
                <>
                  <ExpandLessIcon className="h-4 w-4" />
                  Show less
                </>
              ) : (
                <>
                  <ExpandMoreIcon className="h-4 w-4" />
                  Show {shipmentsWithETA.length - maxShipments} more
                </>
              )}
            </Button>
          </div>
        )}

        {/* Table View for Details */}
        {expanded && (
          <div className="mt-4">
            <TableContainer className="border rounded-lg">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead>TO #</TableHead>
                    <TableHead>Origin</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Order Period</TableHead>
                    <TableHead className="text-right">Arrival Period</TableHead>
                    <TableHead className="text-right">ETA</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shipmentsWithETA.map((shipment, idx) => (
                    <TableRow key={idx} className="hover:bg-muted/30">
                      <TableCell>
                        <span className="text-xs text-muted-foreground">
                          {shipment.to_number || `TO-${idx + 1}`}
                        </span>
                      </TableCell>
                      <TableCell>{shipment.origin || 'Upstream'}</TableCell>
                      <TableCell className="text-right font-semibold">
                        {shipment.quantity}
                      </TableCell>
                      <TableCell className="text-right">
                        {shipment.order_round || 'N/A'}
                      </TableCell>
                      <TableCell className="text-right">
                        {shipment.arrival_round || 'N/A'}
                      </TableCell>
                      <TableCell className="text-right">
                        {shipment.roundsUntilArrival !== null ? (
                          <Badge
                            size="sm"
                            variant={
                              shipment.roundsUntilArrival === 0
                                ? 'success'
                                : shipment.roundsUntilArrival === 1
                                ? 'warning'
                                : 'secondary'
                            }
                          >
                            {shipment.roundsUntilArrival === 0
                              ? 'Arriving!'
                              : `${shipment.roundsUntilArrival} rounds`}
                          </Badge>
                        ) : (
                          'N/A'
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default PipelineVisibility;
