/**
 * Order Planning & Tracking Dashboard
 *
 * AWS SC-inspired order management and tracking interface.
 */

import React, { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Label,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/common';
import { Truck, Filter, Download, RefreshCw } from 'lucide-react';

const OrderPlanning = () => {
  const [filterStatus, setFilterStatus] = useState('all');

  const mockOrders = [
    {
      id: 'ORD-001',
      from: 'Retailer',
      to: 'Wholesaler',
      quantity: 4,
      status: 'in_transit',
      eta: '2 days',
    },
    {
      id: 'ORD-002',
      from: 'Wholesaler',
      to: 'Distributor',
      quantity: 8,
      status: 'processing',
      eta: '4 days',
    },
    {
      id: 'ORD-003',
      from: 'Distributor',
      to: 'Factory',
      quantity: 12,
      status: 'delivered',
      eta: 'Completed',
    },
  ];

  const getStatusVariant = (status) => {
    const variants = {
      in_transit: 'info',
      processing: 'warning',
      delivered: 'success',
      delayed: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-8 flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Truck className="h-10 w-10 text-primary" />
          <h1 className="text-3xl font-bold">Order Planning & Tracking</h1>
        </div>

        <div className="flex gap-2">
          <Button variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <p className="text-muted-foreground">
            Track orders in real-time across your supply chain network. Monitor order status,
            estimated arrival times, and identify potential delays.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Total Orders</p>
            <p className="text-4xl font-bold">24</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">In Transit</p>
            <p className="text-4xl font-bold text-blue-500">8</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Processing</p>
            <p className="text-4xl font-bold text-amber-500">5</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Delayed</p>
            <p className="text-4xl font-bold text-red-500">2</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-4 flex-wrap">
            <Filter className="h-5 w-5" />
            <div className="min-w-[200px]">
              <Label htmlFor="status-filter" className="sr-only">Filter by Status</Label>
              <select
                id="status-filter"
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="all">All Orders</option>
                <option value="in_transit">In Transit</option>
                <option value="processing">Processing</option>
                <option value="delivered">Delivered</option>
                <option value="delayed">Delayed</option>
              </select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order ID</TableHead>
                <TableHead>From</TableHead>
                <TableHead>To</TableHead>
                <TableHead className="text-right">Quantity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>ETA</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockOrders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="font-semibold">{order.id}</TableCell>
                  <TableCell>{order.from}</TableCell>
                  <TableCell>{order.to}</TableCell>
                  <TableCell className="text-right">{order.quantity}</TableCell>
                  <TableCell>
                    <Badge variant={getStatusVariant(order.status)}>
                      {order.status.replace('_', ' ').toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell>{order.eta}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Showing recent orders. Full order history and advanced tracking features coming soon.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default OrderPlanning;
