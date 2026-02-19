/**
 * AgentReportPanel Component - Placeholder
 *
 * This component is a placeholder for the Agent Report Panel feature.
 * Full implementation pending.
 */

import React from 'react';
import { Sheet, SheetContent } from "../ui/sheet";
import { Button } from "../ui/button";

interface AgentReportPanelProps {
  open?: boolean;
  onClose?: () => void;
  data?: any;
  productLink?: string | null;
  dataParam?: string | null;
  skuId?: number | null;
  onUpdateStatus?: (productLink: string, newStatus: 'Submitted' | 'Pending') => void;
  children?: React.ReactNode;
}

export const AgentReportPanel: React.FC<AgentReportPanelProps> = ({
  open = false,
  onClose,
  children
}) => {
  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose?.()}>
      <SheetContent className="w-[400px] sm:w-[540px]">
        <div className="p-4">
          <h2 className="text-lg font-semibold mb-4">Agent Report</h2>
          <p className="text-muted-foreground">
            Agent report panel coming soon.
          </p>
          {children}
          <div className="mt-4">
            <Button onClick={onClose}>Close</Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default AgentReportPanel;
