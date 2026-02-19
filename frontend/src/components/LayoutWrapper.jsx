/**
 * Layout Wrapper Component
 *
 * Wraps the page content with Layout for authenticated routes.
 * Extracted for use with React Router.
 */

import React from 'react';
import Layout from './Layout';
import { Outlet } from 'react-router-dom';

const LayoutWrapper = () => {
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
};

export default LayoutWrapper;
