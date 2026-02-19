import React, { useState } from 'react';
import PageLayout from '../components/PageLayout';
import {
  Button,
  Card,
  CardContent,
  Label,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/common';
import {
  Activity,
  BarChart3,
  Table as TableIcon,
  Download,
  RefreshCw,
  Filter,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

// Sample data for analysis
const sampleTimeSeriesData = [
  { week: 'W1', inventory: 4000, demand: 4200, orders: 5000 },
  { week: 'W2', inventory: 4800, demand: 3800, orders: 4500 },
  { week: 'W3', inventory: 5500, demand: 5200, orders: 5000 },
  { week: 'W4', inventory: 4300, demand: 4500, orders: 4800 },
  { week: 'W5', inventory: 3700, demand: 4000, orders: 4500 },
  { week: 'W6', inventory: 4200, demand: 4100, orders: 5000 },
];

const samplePerformanceData = [
  { metric: 'Total Cost', value: 24567, unit: '$', change: 5.2, trend: 'up' },
  { metric: 'Average Inventory', value: 2345, unit: 'units', change: -2.1, trend: 'down' },
  { metric: 'Service Level', value: 94.5, unit: '%', change: 1.2, trend: 'up' },
  { metric: 'Order Fulfillment', value: 98.2, unit: '%', change: 0.8, trend: 'up' },
  { metric: 'Backorders', value: 45, unit: 'units', change: -12.3, trend: 'down' },
  { metric: 'Lead Time', value: 2.3, unit: 'days', change: -0.5, trend: 'down' },
];

const sampleBullwhipData = [
  { name: 'Retailer', value: 1.2 },
  { name: 'Distributor', value: 1.8 },
  { name: 'Wholesaler', value: 2.3 },
  { name: 'Manufacturer', value: 2.9 },
];

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

const Analysis = () => {
  const [tabValue, setTabValue] = useState('overview');
  const [timeRange, setTimeRange] = useState('last6');
  const [nodeFilter, setNodeFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5);

  const handleChangePage = (newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const totalPages = Math.ceil(samplePerformanceData.length / rowsPerPage);

  return (
    <PageLayout title="Supply Chain Analysis">
      <Tabs value={tabValue} onValueChange={setTabValue} className="mb-6">
        <TabsList>
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="bullwhip" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Bullwhip Effect
          </TabsTrigger>
          <TabsTrigger value="detailed" className="flex items-center gap-2">
            <TableIcon className="h-4 w-4" />
            Detailed Analysis
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {samplePerformanceData.map((item, index) => (
              <Card key={index}>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground mb-1">{item.metric}</p>
                  <div className="flex items-end gap-2 mb-1">
                    <p className="text-3xl font-bold">{item.value}</p>
                    <p className="text-muted-foreground mb-1">{item.unit}</p>
                  </div>
                  <p className={`text-sm ${item.trend === 'up' ? 'text-green-600' : 'text-red-600'}`}>
                    {item.trend === 'up' ? '↑' : '↓'} {Math.abs(item.change)}% from last period
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Inventory & Demand Over Time</h3>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={sampleTimeSeriesData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="week" />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <Tooltip />
                    <Legend />
                    <Line yAxisId="left" type="monotone" dataKey="inventory" stroke="#8884d8" name="Inventory Level" />
                    <Line yAxisId="right" type="monotone" dataKey="demand" stroke="#82ca9d" name="Demand" />
                    <Line yAxisId="right" type="monotone" dataKey="orders" stroke="#ffc658" name="Orders" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="bullwhip">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <Card>
              <CardContent className="pt-6">
                <h3 className="text-lg font-semibold mb-2">Bullwhip Effect Analysis</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  The bullwhip effect shows how demand variability increases as we move up the supply chain.
                </p>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={sampleBullwhipData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis label={{ value: 'Variability', angle: -90, position: 'insideLeft' }} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="value" name="Demand Variability" fill="#8884d8">
                        {sampleBullwhipData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <h3 className="text-lg font-semibold mb-4">Bullwhip Effect by Node</h3>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={sampleBullwhipData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                        nameKey="name"
                        label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                      >
                        {sampleBullwhipData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Bullwhip Effect Mitigation Strategies</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h4 className="font-medium mb-2">Causes of Bullwhip Effect:</h4>
                  <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                    <li>Demand forecast updating</li>
                    <li>Order batching</li>
                    <li>Price fluctuations</li>
                    <li>Rationing and shortage gaming</li>
                  </ul>
                </div>
                <div>
                  <h4 className="font-medium mb-2">Mitigation Strategies:</h4>
                  <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                    <li>Implement Vendor Managed Inventory (VMI)</li>
                    <li>Improve information sharing</li>
                    <li>Reduce lead times</li>
                    <li>Use smaller order quantities</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="detailed">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div>
              <Label htmlFor="time-range">Time Range</Label>
              <select
                id="time-range"
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="last6">Last 6 Weeks</option>
                <option value="last12">Last 12 Weeks</option>
                <option value="ytd">Year to Date</option>
                <option value="custom">Custom Range</option>
              </select>
            </div>
            <div>
              <Label htmlFor="node-filter">Node Filter</Label>
              <select
                id="node-filter"
                value={nodeFilter}
                onChange={(e) => setNodeFilter(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="all">All Nodes</option>
                <option value="retailer">Retailer</option>
                <option value="distributor">Distributor</option>
                <option value="warehouse">Warehouse</option>
                <option value="manufacturer">Manufacturer</option>
              </select>
            </div>
            <div className="flex items-end gap-2">
              <Button variant="outline" className="flex-1">
                <Filter className="h-4 w-4 mr-2" />
                Filters
              </Button>
              <Button variant="outline">
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <Card>
            <CardContent className="pt-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">Performance Metrics</h3>
                <Button variant="ghost" size="icon">
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead className="text-right">Current</TableHead>
                    <TableHead className="text-right">Min</TableHead>
                    <TableHead className="text-right">Max</TableHead>
                    <TableHead className="text-right">Avg</TableHead>
                    <TableHead className="text-right">Target</TableHead>
                    <TableHead className="text-right">Variance</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {samplePerformanceData
                    .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                    .map((row, index) => (
                      <TableRow key={index}>
                        <TableCell>{row.metric}</TableCell>
                        <TableCell className="text-right">
                          {row.value} {row.unit}
                        </TableCell>
                        <TableCell className="text-right">
                          {(row.value * 0.8).toFixed(1)} {row.unit}
                        </TableCell>
                        <TableCell className="text-right">
                          {(row.value * 1.3).toFixed(1)} {row.unit}
                        </TableCell>
                        <TableCell className="text-right">
                          {(row.value * 1.05).toFixed(1)} {row.unit}
                        </TableCell>
                        <TableCell className="text-right">
                          {(row.value * 0.95).toFixed(1)} {row.unit}
                        </TableCell>
                        <TableCell className={`text-right font-medium ${row.trend === 'up' ? 'text-green-600' : 'text-red-600'}`}>
                          {row.trend === 'up' ? '+' : ''}{row.change}%
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4">
                <div className="flex items-center gap-2">
                  <Label htmlFor="rows-per-page">Rows per page:</Label>
                  <select
                    id="rows-per-page"
                    value={rowsPerPage}
                    onChange={handleChangeRowsPerPage}
                    className="h-8 px-2 rounded-md border border-input bg-background text-sm"
                  >
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                    <option value={25}>25</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    Page {page + 1} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleChangePage(page - 1)}
                    disabled={page === 0}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleChangePage(page + 1)}
                    disabled={page >= totalPages - 1}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
};

export default Analysis;
