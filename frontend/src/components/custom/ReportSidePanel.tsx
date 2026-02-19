/**
 * ReportSidePanel Component - Placeholder
 */

import React from 'react';
import { Sheet, SheetContent } from "../ui/sheet";
import { Button } from "../ui/button";

interface ReportSidePanelProps {
  open?: boolean;
  onClose?: () => void;
  data?: any;
  children?: React.ReactNode;
}

export const ReportSidePanel: React.FC<ReportSidePanelProps> = ({
  open = false,
  onClose,
  children
}) => {
  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose?.()}>
      <SheetContent className="w-[400px] sm:w-[540px]">
        <div className="p-4">
          <h2 className="text-lg font-semibold mb-4">Report</h2>
          {children}
          <div className="mt-4">
            <Button onClick={onClose}>Close</Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default ReportSidePanel;
