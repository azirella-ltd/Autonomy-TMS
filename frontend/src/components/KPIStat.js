import React from 'react';
import { Card, CardContent } from './common';

const KPIStat = ({ title, value, subtitle, delta, deltaPositive }) => {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-3xl font-bold">{value}</span>
          {delta && (
            <span className={`font-semibold ${deltaPositive ? 'text-green-600' : 'text-red-600'}`}>
              {delta}
            </span>
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
};

export default KPIStat;
