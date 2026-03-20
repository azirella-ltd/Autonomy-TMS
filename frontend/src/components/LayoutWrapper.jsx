/**
 * Layout Wrapper Component
 *
 * Wraps the page content with the tabbed WorkspaceShell.
 * React Router's Outlet is rendered inside the active tab pane.
 */

import React from 'react';
import WorkspaceShell from './WorkspaceShell';
import DemoSessionTimer from './DemoSessionTimer';

const LayoutWrapper = () => {
  return (
    <>
      <DemoSessionTimer />
      <WorkspaceShell />
    </>
  );
};

export default LayoutWrapper;
