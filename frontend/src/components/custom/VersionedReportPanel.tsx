/**
 * VersionedReportPanel Component - Placeholder
 */

import React from 'react';

interface VersionedReportPanelProps {
  data?: any;
  version?: string;
  children?: React.ReactNode;
}

export const VersionedReportPanel: React.FC<VersionedReportPanelProps> = ({ children }) => {
  return <div className="versioned-report-panel">{children}</div>;
};

export default VersionedReportPanel;
