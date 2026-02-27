/**
 * Override Approval Dialog Component
 *
 * Phase 2: Agent Copilot Mode
 * Modal dialog displayed when human override exceeds authority threshold.
 * Shows impact preview, requests manager approval, and displays pending status.
 *
 * Props:
 * - open: Whether dialog is open
 * - onClose: Callback when dialog closes
 * - overrideData: Authority check result with override details
 * - onApprove: Callback when manager approves (admin only)
 * - onReject: Callback when manager rejects (admin only)
 * - userRole: Current user's role (to show approval buttons)
 */

import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Hourglass,
  Gavel,
  TrendingUp,
} from 'lucide-react';
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Alert,
  AlertTitle,
  AlertDescription,
  Chip,
  Table,
  TableBody,
  TableRow,
  TableCell,
  TableContainer,
  Progress,
  Spinner,
} from '../common';
import { cn } from '../../lib/utils/cn';

const OverrideApprovalDialog = ({
  open,
  onClose,
  overrideData,
  onApprove,
  onReject,
  userRole = 'user',
}) => {
  const [approvalStatus, setApprovalStatus] = useState('pending'); // 'pending', 'approved', 'rejected'
  const [submitting, setSubmitting] = useState(false);

  // Reset status when dialog opens
  useEffect(() => {
    if (open) {
      setApprovalStatus('pending');
      setSubmitting(false);
    }
  }, [open]);

  if (!overrideData) {
    return null;
  }

  const {
    override_approved,
    requires_approval,
    authority_level,
    threshold_exceeded,
    override_percentage,
    threshold_percentage,
    decision_proposal_id,
  } = overrideData;

  // Determine if user can approve/reject
  const canApprove = ['manager', 'executive', 'admin'].includes(userRole.toLowerCase());

  // Get authority level variant
  const getAuthorityVariant = (level) => {
    const variants = {
      OPERATOR: 'outline',
      SUPERVISOR: 'default',
      MANAGER: 'secondary',
      EXECUTIVE: 'success',
    };
    return variants[level] || 'outline';
  };

  // Handle approve
  const handleApprove = async () => {
    setSubmitting(true);
    try {
      await onApprove(decision_proposal_id);
      setApprovalStatus('approved');
      setTimeout(() => {
        onClose();
      }, 2000); // Auto-close after 2 seconds
    } catch (err) {
      console.error('Approval failed:', err);
      alert('Failed to approve override. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Handle reject
  const handleReject = async () => {
    setSubmitting(true);
    try {
      await onReject(decision_proposal_id);
      setApprovalStatus('rejected');
      setTimeout(() => {
        onClose();
      }, 2000); // Auto-close after 2 seconds
    } catch (err) {
      console.error('Rejection failed:', err);
      alert('Failed to reject override. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Get border color class based on status
  const getBorderColorClass = () => {
    if (approvalStatus === 'pending') return 'border-t-4 border-t-warning';
    return 'border-t-4 border-t-destructive';
  };

  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      size="lg"
      closeOnOverlayClick={approvalStatus !== 'pending'}
      closeOnEsc={approvalStatus !== 'pending'}
      className={getBorderColorClass()}
    >
      <ModalHeader>
        <div className="flex items-center gap-3">
          {approvalStatus === 'pending' && (
            <AlertTriangle className="h-8 w-8 text-warning" />
          )}
          {approvalStatus === 'approved' && (
            <CheckCircle2 className="h-8 w-8 text-emerald-500" />
          )}
          {approvalStatus === 'rejected' && (
            <XCircle className="h-8 w-8 text-destructive" />
          )}
          <div>
            <h2 className="text-lg font-semibold">
              {approvalStatus === 'pending' && 'Override Approval Required'}
              {approvalStatus === 'approved' && 'Override Approved'}
              {approvalStatus === 'rejected' && 'Override Rejected'}
            </h2>
            <p className="text-sm text-muted-foreground">
              Decision Proposal #{decision_proposal_id || 'N/A'}
            </p>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        <div className="space-y-6">
          {/* Status Alert */}
          {approvalStatus === 'pending' && (
            <Alert variant="warning" icon={Hourglass}>
              <AlertTitle>Waiting for Manager Approval</AlertTitle>
              <AlertDescription>
                Your decision exceeds your authority level. The game is paused until a manager
                reviews and accepts or rejects your override.
              </AlertDescription>
            </Alert>
          )}

          {approvalStatus === 'approved' && (
            <Alert variant="success" icon={CheckCircle2}>
              <AlertTitle>Override Approved</AlertTitle>
              <AlertDescription>
                A manager has approved your override. The game will resume with your decision.
              </AlertDescription>
            </Alert>
          )}

          {approvalStatus === 'rejected' && (
            <Alert variant="error" icon={XCircle}>
              <AlertTitle>Override Rejected</AlertTitle>
              <AlertDescription>
                A manager has rejected your override. The agent recommendation will be used instead.
              </AlertDescription>
            </Alert>
          )}

          {/* Authority Info */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Gavel className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium">Authority Check</span>
            </div>

            <TableContainer>
              <Table>
                <TableBody>
                  <TableRow>
                    <TableCell>Your Authority Level</TableCell>
                    <TableCell className="text-right">
                      <Chip
                        variant={getAuthorityVariant(authority_level)}
                        size="sm"
                      >
                        {authority_level}
                      </Chip>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Override Percentage</TableCell>
                    <TableCell className="text-right">
                      <span
                        className={cn(
                          'text-sm font-bold',
                          threshold_exceeded ? 'text-destructive' : 'text-foreground'
                        )}
                      >
                        {override_percentage.toFixed(1)}%
                      </span>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Authority Threshold</TableCell>
                    <TableCell className="text-right">
                      <span className="text-sm">{threshold_percentage.toFixed(1)}%</span>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Threshold Exceeded</TableCell>
                    <TableCell className="text-right">
                      <Chip
                        variant={threshold_exceeded ? 'destructive' : 'success'}
                        size="sm"
                      >
                        {threshold_exceeded ? 'Yes' : 'No'}
                      </Chip>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </div>

          {/* Override Progress Bar */}
          <div>
            <p className="text-xs text-muted-foreground mb-2">
              Override Severity
            </p>
            <Progress
              value={Math.min(100, override_percentage)}
              className={cn(
                'h-2.5 rounded',
                override_percentage > 50
                  ? '[&>div]:bg-destructive'
                  : '[&>div]:bg-warning'
              )}
            />
            <div className="flex justify-between mt-1">
              <span className="text-xs text-muted-foreground">0%</span>
              <span className="text-xs font-bold">{override_percentage.toFixed(1)}%</span>
              <span className="text-xs text-muted-foreground">100%</span>
            </div>
          </div>

          {/* Impact Preview (if available) */}
          {overrideData.business_case_preview && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="h-5 w-5 text-muted-foreground" />
                <span className="text-sm font-medium">Business Impact Preview</span>
              </div>

              <div className="rounded-lg border bg-card p-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">
                      Expected Cost Increase
                    </span>
                    <span className="text-sm font-bold text-destructive">
                      ${overrideData.business_case_preview.expected_cost_increase.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">
                      Expected Fill Rate Improvement
                    </span>
                    <span className="text-sm font-bold text-emerald-600">
                      +{(overrideData.business_case_preview.expected_fill_rate_improvement * 100).toFixed(1)}%
                    </span>
                  </div>
                  <hr className="border-border" />
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-bold">Recommendation</span>
                    <Chip
                      variant={
                        overrideData.business_case_preview.recommendation.includes('APPROVE')
                          ? 'success'
                          : 'warning'
                      }
                      size="sm"
                    >
                      {overrideData.business_case_preview.recommendation}
                    </Chip>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Waiting Message (for non-managers) */}
          {!canApprove && approvalStatus === 'pending' && (
            <Alert variant="info">
              <AlertTitle>Scenario Paused</AlertTitle>
              <AlertDescription>
                The game is paused while a manager reviews your decision. You can wait here or come
                back later. You'll be notified when a decision is made.
              </AlertDescription>
            </Alert>
          )}
        </div>
      </ModalBody>

      <ModalFooter>
        {/* Manager Actions */}
        {canApprove && approvalStatus === 'pending' && (
          <>
            <Button
              onClick={handleReject}
              variant="destructive"
              leftIcon={<XCircle className="h-4 w-4" />}
              disabled={submitting}
            >
              Reject Override
            </Button>
            <Button
              onClick={handleApprove}
              variant="default"
              leftIcon={<CheckCircle2 className="h-4 w-4" />}
              disabled={submitting}
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {submitting ? 'Approving...' : 'Approve Override'}
            </Button>
          </>
        )}

        {/* ScenarioUser Actions */}
        {!canApprove && approvalStatus === 'pending' && (
          <Button onClick={onClose} variant="outline" disabled={submitting}>
            Wait for Approval
          </Button>
        )}

        {/* Close Button (after approval/rejection) */}
        {approvalStatus !== 'pending' && (
          <Button onClick={onClose} variant="default">
            Close
          </Button>
        )}

        {/* Loading Indicator */}
        {submitting && <Spinner size="sm" className="ml-2" />}
      </ModalFooter>
    </Modal>
  );
};

export default OverrideApprovalDialog;
