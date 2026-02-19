import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Spinner,
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/common';
import {
  Plus,
  Pencil,
  Trash2,
  Search,
  TrendingUp,
  MapPin,
  Building2,
  BarChart3,
  Link2,
} from 'lucide-react';
import { api } from '../services/api';

const SupplierManagement = () => {
  const [tabValue, setTabValue] = useState('suppliers');
  const [suppliers, setSuppliers] = useState([]);
  const [vendorProducts, setVendorProducts] = useState([]);
  const [vendorLeadTimes, setVendorLeadTimes] = useState([]);
  const [performanceRecords, setPerformanceRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Pagination
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [totalSuppliers, setTotalSuppliers] = useState(0);

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [filterIsActive, setFilterIsActive] = useState('true');
  const [filterTier, setFilterTier] = useState('');
  const [filterCountry, setFilterCountry] = useState('');

  // Load suppliers
  const loadSuppliers = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        page: page + 1,
        page_size: pageSize,
        tpartner_type: 'vendor',
      };

      if (searchTerm) params.search = searchTerm;
      if (filterIsActive) params.is_active = filterIsActive;
      if (filterTier) params.tier = filterTier;
      if (filterCountry) params.country = filterCountry;

      const response = await api.get('/suppliers/suppliers', { params });
      setSuppliers(response.data.items);
      setTotalSuppliers(response.data.total);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load suppliers');
    } finally {
      setLoading(false);
    }
  };

  // Load summary
  const loadSummary = async () => {
    try {
      const response = await api.get('/suppliers/suppliers/summary', {
        params: { tpartner_type: 'vendor' }
      });
      setSummary(response.data);
    } catch (err) {
      console.error('Failed to load summary:', err);
    }
  };

  // Load vendor products
  const loadVendorProducts = async () => {
    setLoading(true);
    try {
      const response = await api.get('/suppliers/vendor-products', {
        params: { page: page + 1, page_size: pageSize }
      });
      setVendorProducts(response.data.items);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load vendor products');
    } finally {
      setLoading(false);
    }
  };

  // Load vendor lead times
  const loadVendorLeadTimes = async () => {
    setLoading(true);
    try {
      const response = await api.get('/suppliers/vendor-lead-times', {
        params: { page: page + 1, page_size: pageSize }
      });
      setVendorLeadTimes(response.data.items);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load lead times');
    } finally {
      setLoading(false);
    }
  };

  // Load performance records
  const loadPerformanceRecords = async () => {
    setLoading(true);
    try {
      const response = await api.get('/suppliers/supplier-performance', {
        params: { page: page + 1, page_size: pageSize }
      });
      setPerformanceRecords(response.data.items);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load performance records');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tabValue === 'suppliers') {
      loadSuppliers();
      loadSummary();
    } else if (tabValue === 'products') {
      loadVendorProducts();
    } else if (tabValue === 'leadtimes') {
      loadVendorLeadTimes();
    } else if (tabValue === 'performance') {
      loadPerformanceRecords();
    }
  }, [tabValue, page, pageSize, searchTerm, filterIsActive, filterTier, filterCountry]);

  const handleSearch = () => {
    setPage(0);
    loadSuppliers();
  };

  const handleDeleteSupplier = async (supplier) => {
    if (!window.confirm(`Are you sure you want to delete supplier ${supplier.id}?`)) {
      return;
    }

    try {
      await api.delete(`/suppliers/suppliers/${supplier.id}`, {
        params: {
          tpartner_type: supplier.tpartner_type,
          geo_id: supplier.geo_id,
          eff_start_date: supplier.eff_start_date
        }
      });
      loadSuppliers();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete supplier');
    }
  };

  const getStatusBadge = (isActive) => (
    <Badge variant={isActive === 'true' ? 'success' : 'secondary'}>
      {isActive === 'true' ? 'Active' : 'Inactive'}
    </Badge>
  );

  const getTierBadge = (tier) => {
    const variants = {
      TIER_1: 'destructive',
      TIER_2: 'warning',
      TIER_3: 'info',
      TIER_4: 'secondary'
    };
    return tier ? (
      <Badge variant={variants[tier] || 'secondary'}>{tier}</Badge>
    ) : (
      <Badge variant="outline">Unassigned</Badge>
    );
  };

  const getPerformanceColor = (score) => {
    if (!score) return 'text-muted-foreground';
    if (score >= 90) return 'text-green-600';
    if (score >= 75) return 'text-amber-500';
    return 'text-red-500';
  };

  const formatPercent = (value) => {
    return value !== null && value !== undefined ? `${value.toFixed(1)}%` : 'N/A';
  };

  // Tab: Suppliers List
  const renderSuppliersTab = () => (
    <div className="space-y-6">
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-4xl font-bold text-primary">{summary.total_suppliers}</p>
              <p className="text-sm text-muted-foreground">Total Suppliers</p>
              <p className="text-xs text-green-600">{summary.active_suppliers} active</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-4xl font-bold text-primary">{formatPercent(summary.avg_on_time_delivery)}</p>
              <p className="text-sm text-muted-foreground">Avg On-Time Delivery</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-4xl font-bold text-primary">{formatPercent(summary.avg_quality_rating)}</p>
              <p className="text-sm text-muted-foreground">Avg Quality Rating</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-4xl font-bold text-red-500">{summary.high_risk_count}</p>
              <p className="text-sm text-muted-foreground">High Risk Suppliers</p>
              <p className="text-xs text-green-600">{summary.iso_certified_count} ISO certified</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
            <div className="md:col-span-2">
              <Label>Search</Label>
              <div className="flex gap-2 mt-1">
                <Input
                  placeholder="Search by ID or description"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                />
                <Button variant="ghost" size="icon" onClick={handleSearch}>
                  <Search className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div>
              <Label>Status</Label>
              <select
                value={filterIsActive}
                onChange={(e) => setFilterIsActive(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">All</option>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </select>
            </div>
            <div>
              <Label>Tier</Label>
              <select
                value={filterTier}
                onChange={(e) => setFilterTier(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">All</option>
                <option value="TIER_1">Tier 1</option>
                <option value="TIER_2">Tier 2</option>
                <option value="TIER_3">Tier 3</option>
                <option value="TIER_4">Tier 4</option>
              </select>
            </div>
            <div>
              <Button className="w-full">
                <Plus className="h-4 w-4 mr-2" />
                New Supplier
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Suppliers Table */}
      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier ID</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Tier</TableHead>
                <TableHead>Country</TableHead>
                <TableHead>On-Time</TableHead>
                <TableHead>Quality</TableHead>
                <TableHead>Performance</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8">
                    <Spinner />
                  </TableCell>
                </TableRow>
              ) : suppliers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8 text-muted-foreground">
                    No suppliers found
                  </TableCell>
                </TableRow>
              ) : (
                suppliers.map((supplier) => (
                  <TableRow key={`${supplier.id}-${supplier.eff_start_date}`}>
                    <TableCell>
                      <p className="font-bold">{supplier.id}</p>
                      {supplier.geo_id && (
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <MapPin className="h-3 w-3" /> {supplier.geo_id}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <p>{supplier.description}</p>
                      {supplier.contact_email && (
                        <p className="text-xs text-muted-foreground">{supplier.contact_email}</p>
                      )}
                    </TableCell>
                    <TableCell>{getStatusBadge(supplier.is_active)}</TableCell>
                    <TableCell>{getTierBadge(supplier.tier)}</TableCell>
                    <TableCell>{supplier.country || '-'}</TableCell>
                    <TableCell className={getPerformanceColor(supplier.on_time_delivery_rate)}>
                      {formatPercent(supplier.on_time_delivery_rate)}
                    </TableCell>
                    <TableCell className={getPerformanceColor(supplier.quality_rating)}>
                      {formatPercent(supplier.quality_rating)}
                    </TableCell>
                    <TableCell className={`font-bold ${getPerformanceColor(supplier.performance_score)}`}>
                      {formatPercent(supplier.performance_score)}
                    </TableCell>
                    <TableCell>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Edit</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" onClick={() => handleDeleteSupplier(supplier)}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Showing {suppliers.length} of {totalSuppliers} suppliers
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={suppliers.length < pageSize}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // Tab: Vendor Products
  const renderVendorProductsTab = () => (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Vendor-Product Associations</h2>
        <Button>
          <Link2 className="h-4 w-4 mr-2" />
          New Association
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier ID</TableHead>
                <TableHead>Product ID</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Primary</TableHead>
                <TableHead>Unit Cost</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>MOQ</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8">
                    <Spinner />
                  </TableCell>
                </TableRow>
              ) : vendorProducts.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8 text-muted-foreground">
                    No vendor-product associations found
                  </TableCell>
                </TableRow>
              ) : (
                vendorProducts.map((vp) => (
                  <TableRow key={vp.id}>
                    <TableCell>{vp.tpartner_id}</TableCell>
                    <TableCell>{vp.product_id}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">Priority {vp.priority}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={vp.is_primary ? 'default' : 'outline'}>
                        {vp.is_primary ? 'Primary' : 'Secondary'}
                      </Badge>
                    </TableCell>
                    <TableCell>${vp.vendor_unit_cost.toFixed(2)}</TableCell>
                    <TableCell>{vp.currency}</TableCell>
                    <TableCell>{vp.minimum_order_quantity || '-'}</TableCell>
                    <TableCell>{getStatusBadge(vp.is_active)}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon">
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );

  // Tab: Lead Times
  const renderLeadTimesTab = () => (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Vendor Lead Times</h2>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          New Lead Time
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier ID</TableHead>
                <TableHead>Product ID</TableHead>
                <TableHead>Site ID</TableHead>
                <TableHead>Lead Time (days)</TableHead>
                <TableHead>Variability (days)</TableHead>
                <TableHead>Effective Dates</TableHead>
                <TableHead>Specificity Level</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8">
                    <Spinner />
                  </TableCell>
                </TableRow>
              ) : vendorLeadTimes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                    No lead times found
                  </TableCell>
                </TableRow>
              ) : (
                vendorLeadTimes.map((lt) => (
                  <TableRow key={lt.id}>
                    <TableCell>{lt.tpartner_id}</TableCell>
                    <TableCell>{lt.product_id || '-'}</TableCell>
                    <TableCell>{lt.site_id || '-'}</TableCell>
                    <TableCell className="font-bold">{lt.lead_time_days}</TableCell>
                    <TableCell>
                      {lt.lead_time_variability_days ? `±${lt.lead_time_variability_days}` : '-'}
                    </TableCell>
                    <TableCell>
                      <p className="text-xs">
                        {new Date(lt.eff_start_date).toLocaleDateString()}
                        {lt.eff_end_date && ` - ${new Date(lt.eff_end_date).toLocaleDateString()}`}
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {lt.product_id ? 'Product' : lt.site_id ? 'Site' : 'Company'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );

  // Tab: Performance
  const renderPerformanceTab = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Supplier Performance Records</h2>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier ID</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Orders Placed</TableHead>
                <TableHead>On-Time Rate</TableHead>
                <TableHead>Quality Rating</TableHead>
                <TableHead>Performance Score</TableHead>
                <TableHead>Total Spend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8">
                    <Spinner />
                  </TableCell>
                </TableRow>
              ) : performanceRecords.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                    No performance records found
                  </TableCell>
                </TableRow>
              ) : (
                performanceRecords.map((perf) => (
                  <TableRow key={perf.id}>
                    <TableCell>{perf.tpartner_id}</TableCell>
                    <TableCell>
                      <p className="text-xs">
                        {new Date(perf.period_start).toLocaleDateString()} -{' '}
                        {new Date(perf.period_end).toLocaleDateString()}
                      </p>
                      <Badge variant="outline" className="mt-1">{perf.period_type}</Badge>
                    </TableCell>
                    <TableCell>{perf.orders_placed}</TableCell>
                    <TableCell className={getPerformanceColor(perf.on_time_delivery_rate)}>
                      {formatPercent(perf.on_time_delivery_rate)}
                    </TableCell>
                    <TableCell className={getPerformanceColor(perf.quality_rating)}>
                      {formatPercent(perf.quality_rating)}
                    </TableCell>
                    <TableCell className={`font-bold ${getPerformanceColor(perf.overall_performance_score)}`}>
                      {formatPercent(perf.overall_performance_score)}
                    </TableCell>
                    <TableCell>
                      ${perf.total_spend.toLocaleString()} {perf.currency}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-6 flex justify-between items-center flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">Supplier Management</h1>
          <p className="text-muted-foreground">AWS Supply Chain Compliant - Trading Partners (type='vendor')</p>
        </div>
        <Badge variant="outline" className="flex items-center gap-2">
          <Building2 className="h-4 w-4" />
          AWS SC Entity #17
        </Badge>
      </div>

      <Tabs value={tabValue} onValueChange={setTabValue}>
        <TabsList className="mb-6">
          <TabsTrigger value="suppliers" className="flex items-center gap-2">
            <Building2 className="h-4 w-4" />
            Suppliers
          </TabsTrigger>
          <TabsTrigger value="products" className="flex items-center gap-2">
            <Link2 className="h-4 w-4" />
            Vendor Products
          </TabsTrigger>
          <TabsTrigger value="leadtimes" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Lead Times
          </TabsTrigger>
          <TabsTrigger value="performance" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Performance
          </TabsTrigger>
        </TabsList>

        <TabsContent value="suppliers">{renderSuppliersTab()}</TabsContent>
        <TabsContent value="products">{renderVendorProductsTab()}</TabsContent>
        <TabsContent value="leadtimes">{renderLeadTimesTab()}</TabsContent>
        <TabsContent value="performance">{renderPerformanceTab()}</TabsContent>
      </Tabs>
    </div>
  );
};

export default SupplierManagement;
