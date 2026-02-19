import React from 'react';
import { Card, CardContent } from './common';

const ChartCard = ({ title, subtitle, height = 320, children, footer }) => {
  return (
    <Card>
      <CardContent className="p-5">
        {title && (
          <h3 className="text-lg font-semibold mb-1">{title}</h3>
        )}
        {subtitle && (
          <p className="text-sm text-muted-foreground mb-2">{subtitle}</p>
        )}
        <div style={{ height }}>
          {children}
        </div>
        {footer}
      </CardContent>
    </Card>
  );
};

export default ChartCard;
