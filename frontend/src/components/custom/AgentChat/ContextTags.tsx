/**
 * ContextTags Component - Placeholder
 */

import React from 'react';

export interface ContextTag {
  id: string;
  label: string;
  type?: string;
}

interface ContextTagsProps {
  tags?: ContextTag[];
  children?: React.ReactNode;
}

export const ContextTags: React.FC<ContextTagsProps> = ({ children }) => {
  return <div className="context-tags">{children}</div>;
};

export default ContextTags;
