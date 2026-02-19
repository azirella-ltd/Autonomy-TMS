/**
 * V4ReportPanel Component - Placeholder
 */

import React from 'react';

interface V4ReportPanelProps {
  data?: any;
  children?: React.ReactNode;
}

export const V4ReportPanel: React.FC<V4ReportPanelProps> = ({ children }) => {
  return <div className="v4-report-panel">{children}</div>;
};

export default V4ReportPanel;
