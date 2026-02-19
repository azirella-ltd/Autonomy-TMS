import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Spinner,
  Modal,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  CheckCircle,
  TrendingUp,
  Calculator,
  RefreshCw,
  Search,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { Line, Bar } from 'react-chartjs-2';
import { api } from '../../services/api';

const ATPCTPView = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [productId, setProductId] = useState('');
  const [siteId, setSiteId] = useState('');
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);

  // ATP data
  const [atpAvailability, setAtpAvailability] = useState(null);
  const [calculateAtpDialogOpen, setCalculateAtpDialogOpen] = useState(false);
  const [atpRequest, setAtpRequest] = useState({
    product_id: '',
    site_id: '',
    start_date: new Date(),
    end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000), // 90 days
    atp_rule: 'cumulative',
  });

  // CTP data
  const [ctpAvailability, setCtpAvailability] = useState(null);
  const [calculateCtpDialogOpen, setCalculateCtpDialogOpen] = useState(false);
  const [ctpRequest, setCtpRequest] = useState({
    product_id: '',
    site_id: '',
    start_date: new Date(),
    end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000),
    include_production_capacity: true,
    check_component_availability: true,
    check_resource_capacity: true,
  });

  // Order promise
  const [promiseDialogOpen, setPromiseDialogOpen] = useState(false);
  const [promiseRequest, setPromiseRequest] = useState({
    order_id: '',
    order_line_number: 1,
    product_id: '',
    site_id: '',
    customer_id: '',
    requested_quantity: 0,
    requested_date: new Date(),
    allow_partial: true,
    allow_substitute: false,
    allow_backorder: true,
  });
  const [promiseResult, setPromiseResult] = useState(null);

  const [activeTab, setActiveTab] = useState('atp');

  useEffect(() => {
    if (productId && siteId) {
      loadData();
    }
  }, [activeTab, productId, siteId, startDate, endDate]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      if (activeTab === 'atp') {
        await loadAtpAvailability();
      } else if (activeTab === 'ctp') {
        await loadCtpAvailability();
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadAtpAvailability = async () => {
    const params = { product_id: productId, site_id: siteId };
    if (startDate) params.start_date = startDate.toISOString().split('T')[0];
    if (endDate) params.end_date = endDate.toISOString().split('T')[0];

    const response = await api.get('/inventory-projection/atp/availability', { params });
    setAtpAvailability(response.data);
  };

  const loadCtpAvailability = async () => {
    const params = { product_id: productId, site_id: siteId };
    if (startDate) params.start_date = startDate.toISOString().split('T')[0];
    if (endDate) params.end_date = endDate.toISOString().split('T')[0];

    const response = await api.get('/inventory-projection/ctp/availability', { params });
    setCtpAvailability(response.data);
  };

  const handleCalculateAtp = async () => {
    try {
      setLoading(true);
      const response = await api.post('/inventory-projection/atp/calculate', atpRequest);
      alert(`ATP calculated successfully! ${response.data.length} periods generated.`);
      setCalculateAtpDialogOpen(false);
      setError(null);
      await loadAtpAvailability();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCalculateCtp = async () => {
    try {
      setLoading(true);
      const response = await api.post('/inventory-projection/ctp/calculate', ctpRequest);
      alert(`CTP calculated successfully! ${response.data.length} periods generated.`);
      setCalculateCtpDialogOpen(false);
      setError(null);
      await loadCtpAvailability();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handlePromiseOrder = async () => {
    try {
      setLoading(true);
      const response = await api.post('/inventory-projection/promise', promiseRequest);
      setPromiseResult(response.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const renderFilters = () => (
    <Card className="mb-6">
      <CardContent className="pt-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
          <div className="space-y-2">
            <Label htmlFor="productId">Product ID *</Label>
            <Input
              id="productId"
              type="number"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              placeholder="Enter product ID"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="siteId">Site ID *</Label>
            <Input
              id="siteId"
              type="number"
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              placeholder="Enter site ID"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="startDate">Start Date</Label>
            <Input
              id="startDate"
              type="date"
              value={startDate ? startDate.toISOString().split('T')[0] : ''}
              onChange={(e) => setStartDate(e.target.value ? new Date(e.target.value) : null)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="endDate">End Date</Label>
            <Input
              id="endDate"
              type="date"
              value={endDate ? endDate.toISOString().split('T')[0] : ''}
              onChange={(e) => setEndDate(e.target.value ? new Date(e.target.value) : null)}
            />
          </div>
          <Button
            onClick={loadData}
            disabled={!productId || !siteId}
            className="w-full"
            leftIcon={<Search className="h-4 w-4" />}
          >
            Search
          </Button>
        </div>
      </CardContent>
    </Card>
  );

  const renderAtpTab = () => (
    <div>
      <div className="flex gap-2 mb-4">
        <Button
          onClick={() => setCalculateAtpDialogOpen(true)}
          leftIcon={<Calculator className="h-4 w-4" />}
        >
          Calculate ATP
        </Button>
        <Button
          variant="outline"
          onClick={() => setPromiseDialogOpen(true)}
          leftIcon={<CheckCircle className="h-4 w-4" />}
        >
          Promise Order
        </Button>
      </div>

      {!productId || !siteId ? (
        <Alert variant="info">
          <Info className="h-4 w-4" />
          <span className="ml-2">Please enter Product ID and Site ID to view ATP availability</span>
        </Alert>
      ) : atpAvailability ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Current ATP</p>
                <p className="text-3xl font-bold text-green-600">
                  {atpAvailability.current_atp?.toFixed(0) || 'N/A'}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Available-to-Promise now
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Total Available</p>
                <p className="text-3xl font-bold text-blue-600">
                  {atpAvailability.total_available?.toFixed(0) || 'N/A'}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Total quantity available
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Uncommitted Inventory</p>
                <p className="text-3xl font-bold text-primary">
                  {atpAvailability.uncommitted_inventory?.toFixed(0) || 'N/A'}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Inventory not yet promised
                </p>
              </CardContent>
            </Card>
          </div>

          {atpAvailability.future_atp && atpAvailability.future_atp.length > 0 && (
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-4">ATP Projection</h3>
                <Line
                  data={{
                    labels: atpAvailability.future_atp.map((a) => a.date),
                    datasets: [
                      {
                        label: 'Cumulative ATP',
                        data: atpAvailability.future_atp.map((a) => a.cumulative_atp),
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.1,
                      },
                      {
                        label: 'Discrete ATP',
                        data: atpAvailability.future_atp.map((a) => a.discrete_atp),
                        borderColor: 'rgb(54, 162, 235)',
                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                        tension: 0.1,
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    plugins: {
                      legend: { position: 'top' },
                      title: {
                        display: true,
                        text: 'ATP Over Time',
                      },
                    },
                    scales: {
                      y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Quantity' },
                      },
                    },
                  }}
                />
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <Alert variant="info">
          No ATP data available. Click "Calculate ATP" to generate.
        </Alert>
      )}
    </div>
  );

  const renderCtpTab = () => (
    <div>
      <div className="mb-4">
        <Button
          onClick={() => setCalculateCtpDialogOpen(true)}
          leftIcon={<Calculator className="h-4 w-4" />}
        >
          Calculate CTP
        </Button>
      </div>

      {!productId || !siteId ? (
        <Alert variant="info">
          <Info className="h-4 w-4" />
          <span className="ml-2">Please enter Product ID and Site ID to view CTP availability</span>
        </Alert>
      ) : ctpAvailability ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Current CTP</p>
                <p className="text-3xl font-bold text-primary">
                  {ctpAvailability.current_ctp?.toFixed(0) || 'N/A'}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Capable-to-Promise now
                </p>
              </CardContent>
            </Card>
            <Card className="md:col-span-2">
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Capacity Constraints</h3>
                {ctpAvailability.constraints && ctpAvailability.constraints.length > 0 ? (
                  <div className="flex gap-2 flex-wrap">
                    {ctpAvailability.constraints.map((c, idx) => (
                      <Badge key={idx} variant="warning" className="flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {c}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <Badge variant="success" className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" />
                    No constraints
                  </Badge>
                )}
              </CardContent>
            </Card>
          </div>

          {ctpAvailability.future_ctp && ctpAvailability.future_ctp.length > 0 && (
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-4">CTP Projection</h3>
                <Bar
                  data={{
                    labels: ctpAvailability.future_ctp.map((c) => c.date),
                    datasets: [
                      {
                        label: 'CTP Quantity',
                        data: ctpAvailability.future_ctp.map((c) => c.ctp_qty),
                        backgroundColor: ctpAvailability.future_ctp.map((c) =>
                          c.constrained
                            ? 'rgba(255, 99, 132, 0.6)'
                            : 'rgba(54, 162, 235, 0.6)'
                        ),
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    plugins: {
                      legend: { position: 'top' },
                      title: {
                        display: true,
                        text: 'CTP Over Time (Red = Constrained)',
                      },
                    },
                    scales: {
                      y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Quantity' },
                      },
                    },
                  }}
                />
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <Alert variant="info">
          No CTP data available. Click "Calculate CTP" to generate.
        </Alert>
      )}
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">ATP/CTP Analysis</h1>
        </div>
        <Button
          variant="outline"
          onClick={loadData}
          disabled={!productId || !siteId}
          leftIcon={<RefreshCw className="h-4 w-4" />}
        >
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {renderFilters()}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="atp" className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4" />
            ATP (Available-to-Promise)
          </TabsTrigger>
          <TabsTrigger value="ctp" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            CTP (Capable-to-Promise)
          </TabsTrigger>
        </TabsList>

        {loading ? (
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        ) : (
          <>
            <TabsContent value="atp">{renderAtpTab()}</TabsContent>
            <TabsContent value="ctp">{renderCtpTab()}</TabsContent>
          </>
        )}
      </Tabs>

      {/* Calculate ATP Dialog */}
      <Modal
        isOpen={calculateAtpDialogOpen}
        onClose={() => setCalculateAtpDialogOpen(false)}
        title="Calculate ATP"
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="atpProductId">Product ID</Label>
            <Input
              id="atpProductId"
              type="number"
              value={atpRequest.product_id}
              onChange={(e) =>
                setAtpRequest({ ...atpRequest, product_id: parseInt(e.target.value) })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="atpSiteId">Site ID</Label>
            <Input
              id="atpSiteId"
              type="number"
              value={atpRequest.site_id}
              onChange={(e) =>
                setAtpRequest({ ...atpRequest, site_id: parseInt(e.target.value) })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="atpRule">ATP Rule</Label>
            <Select
              value={atpRequest.atp_rule}
              onValueChange={(value) => setAtpRequest({ ...atpRequest, atp_rule: value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select ATP rule" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="discrete">Discrete (Period-by-period)</SelectItem>
                <SelectItem value="cumulative">Cumulative (Running total)</SelectItem>
                <SelectItem value="rolling">Rolling (Moving window)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setCalculateAtpDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCalculateAtp} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Calculate
          </Button>
        </div>
      </Modal>

      {/* Calculate CTP Dialog */}
      <Modal
        isOpen={calculateCtpDialogOpen}
        onClose={() => setCalculateCtpDialogOpen(false)}
        title="Calculate CTP"
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ctpProductId">Product ID</Label>
            <Input
              id="ctpProductId"
              type="number"
              value={ctpRequest.product_id}
              onChange={(e) =>
                setCtpRequest({ ...ctpRequest, product_id: parseInt(e.target.value) })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ctpSiteId">Site ID</Label>
            <Input
              id="ctpSiteId"
              type="number"
              value={ctpRequest.site_id}
              onChange={(e) =>
                setCtpRequest({ ...ctpRequest, site_id: parseInt(e.target.value) })
              }
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setCalculateCtpDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCalculateCtp} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Calculate
          </Button>
        </div>
      </Modal>

      {/* Promise Order Dialog */}
      <Modal
        isOpen={promiseDialogOpen}
        onClose={() => {
          setPromiseDialogOpen(false);
          setPromiseResult(null);
        }}
        title="Promise Order"
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="orderId">Order ID</Label>
              <Input
                id="orderId"
                value={promiseRequest.order_id}
                onChange={(e) => setPromiseRequest({ ...promiseRequest, order_id: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="promiseProductId">Product ID</Label>
              <Input
                id="promiseProductId"
                type="number"
                value={promiseRequest.product_id}
                onChange={(e) =>
                  setPromiseRequest({ ...promiseRequest, product_id: parseInt(e.target.value) })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="promiseSiteId">Site ID</Label>
              <Input
                id="promiseSiteId"
                type="number"
                value={promiseRequest.site_id}
                onChange={(e) =>
                  setPromiseRequest({ ...promiseRequest, site_id: parseInt(e.target.value) })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="requestedQuantity">Requested Quantity</Label>
              <Input
                id="requestedQuantity"
                type="number"
                value={promiseRequest.requested_quantity}
                onChange={(e) =>
                  setPromiseRequest({
                    ...promiseRequest,
                    requested_quantity: parseFloat(e.target.value),
                  })
                }
              />
            </div>
          </div>

          {promiseResult && (
            <Alert
              variant={promiseResult.can_promise ? 'success' : 'warning'}
              className="mt-4"
            >
              <div>
                <h4 className="font-semibold text-lg">
                  {promiseResult.can_promise
                    ? 'Order Can Be Promised'
                    : 'Cannot Fully Promise Order'}
                </h4>
                <p className="mt-1">
                  Promised Quantity: {promiseResult.promised_quantity} | Promised Date:{' '}
                  {promiseResult.promised_date} | Source: {promiseResult.promise_source}
                </p>
                <p className="text-sm mt-1">
                  Confidence: {(promiseResult.confidence * 100).toFixed(0)}%
                </p>
                {promiseResult.confidence_factors &&
                  promiseResult.confidence_factors.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {promiseResult.confidence_factors.map((factor, idx) => (
                        <Badge key={idx} variant="secondary">
                          {factor}
                        </Badge>
                      ))}
                    </div>
                  )}
              </div>
            </Alert>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            onClick={() => {
              setPromiseDialogOpen(false);
              setPromiseResult(null);
            }}
          >
            Close
          </Button>
          <Button onClick={handlePromiseOrder} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Promise
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default ATPCTPView;
