/**
 * FindingCard Component - Placeholder
 */

import React from 'react';

interface FindingCardProps {
  finding?: any;
  children?: React.ReactNode;
}

export const FindingCard: React.FC<FindingCardProps> = ({ children }) => {
  return <div className="finding-card">{children}</div>;
};

export default FindingCard;
