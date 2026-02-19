import React from 'react';
import {
  Badge,
  Button,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './common';
import { Pencil } from 'lucide-react';

const rows = [
  { sku: 'SKU-001', product: 'Premium Widget A', category: 'Electronics', current: 2810, forecast: 3200, safety: 500, lead: '14d', trend: 'up', risk: 'low', accuracy: '92.4%' },
  { sku: 'SKU-012', product: 'Industrial Tool I', category: 'Tools', current: 2340, forecast: 2650, safety: 250, lead: '25d', trend: 'down', risk: 'medium', accuracy: '87.6%' },
];

const riskVariant = (risk) => ({
  low: 'success',
  medium: 'warning',
  high: 'destructive',
}[risk] || 'secondary');

const TrendCell = ({ value }) => (
  <span className={
    value === 'up' ? 'text-green-600' :
    value === 'down' ? 'text-red-600' :
    'text-muted-foreground'
  }>
    {value === 'up' ? '↗' : value === 'down' ? '↘' : '→'}
  </span>
);

const SkuTable = () => (
  <Card>
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>SKU</TableHead>
            <TableHead>Product Name</TableHead>
            <TableHead>Category</TableHead>
            <TableHead className="text-right">Current Stock</TableHead>
            <TableHead className="text-right">Forecast Demand</TableHead>
            <TableHead className="text-right">Safety Stock</TableHead>
            <TableHead>Lead Time</TableHead>
            <TableHead>Trend</TableHead>
            <TableHead>Risk Level</TableHead>
            <TableHead>Accuracy</TableHead>
            <TableHead className="text-center">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.sku}>
              <TableCell>{r.sku}</TableCell>
              <TableCell>{r.product}</TableCell>
              <TableCell>{r.category}</TableCell>
              <TableCell className="text-right">{r.current.toLocaleString()}</TableCell>
              <TableCell className="text-right">{r.forecast.toLocaleString()}</TableCell>
              <TableCell className="text-right">{r.safety.toLocaleString()}</TableCell>
              <TableCell>{r.lead}</TableCell>
              <TableCell><TrendCell value={r.trend} /></TableCell>
              <TableCell>
                <Badge variant={riskVariant(r.risk)} className="capitalize">
                  {r.risk}
                </Badge>
              </TableCell>
              <TableCell>{r.accuracy}</TableCell>
              <TableCell className="text-center">
                <Button variant="ghost" size="icon">
                  <Pencil className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  </Card>
);

export default SkuTable;
