/**
 * EditWorkflowCard Component - Placeholder
 */

import React from 'react';

interface EditWorkflowCardProps {
  workflow?: any;
  children?: React.ReactNode;
}

export const EditWorkflowCard: React.FC<EditWorkflowCardProps> = ({ children }) => {
  return <div className="edit-workflow-card">{children}</div>;
};

export default EditWorkflowCard;
