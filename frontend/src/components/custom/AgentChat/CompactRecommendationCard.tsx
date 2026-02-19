/**
 * CompactRecommendationCard Component - Placeholder
 */

import React from 'react';

interface CompactRecommendationCardProps {
  recommendation?: any;
  children?: React.ReactNode;
}

export const CompactRecommendationCard: React.FC<CompactRecommendationCardProps> = ({ children }) => {
  return <div className="compact-recommendation-card">{children}</div>;
};

export default CompactRecommendationCard;
