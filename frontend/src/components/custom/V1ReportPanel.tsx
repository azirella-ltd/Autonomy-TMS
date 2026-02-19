/**
 * V1ReportPanel Component - Placeholder
 */

import React from 'react';

interface V1ReportPanelProps {
  data?: any;
  children?: React.ReactNode;
}

export const V1ReportPanel: React.FC<V1ReportPanelProps> = ({ children }) => {
  return <div className="v1-report-panel">{children}</div>;
};

export default V1ReportPanel;
