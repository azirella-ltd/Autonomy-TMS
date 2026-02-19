import { useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import { Tabs, TabsList, TabsTrigger } from "../ui/tabs";
import { Checkbox } from "../ui/checkbox";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";
import { CheckCircle, Clock, TriangleAlert, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { ReportSidePanel } from "./ReportSidePanel";
import { AgentReportPanel } from "./AgentReportPanel";
import { useFeatureFlags } from "@/contexts/FeatureFlagContext";

interface ForecastItem {
  id: number;
  decision: "Autonomous" | "Suggested";
  productName: string;
  productLink: string;
  category: string;
  smartSortFilter: boolean;
  site: string;
  retailer: string;
  historicalPerformance: {
    wins: number;
    total: number;
    display: string;
    description: string;
  };
  failedValidations: {
    failed: number;
    total: number;
    display: string;
    details: Array<{
      name: string;
      status: string;
      reason: string;
    }>;
  };
  flaggedRevenue: {
    value: number;
    display: string;
    units: string;
  };
  dollarizedVolume: {
    value: number;
    display: string;
    units: string;
  };
  agentEdit: {
    value: number;
    display: string;
    units: string;
  };
  agentReasoning: string;
  status: "Submitted" | "Pending";
  dashbaordData?: string;
}

interface ProductLineItem {
  id: number;
  decision: "Autonomous" | "Suggested";
  forecastLevel: string;
  productName: string;
  productLink: string;
  taxonomy: string;
  smartSortFilter: boolean;
  region: string;
  skuCount: number;
  historicalPerformance: {
    wins: number;
    total: number;
    display: string;
    description: string;
  };
  failedValidations: {
    failed: number;
    total: number;
    display: string;
    details: Array<{
      name: string;
      status: string;
      reason: string;
    }>;
  };
  flaggedRevenue: {
    value: number;
    display: string;
    units: string;
  };
  dollarizedVolume: {
    value: number;
    display: string;
    units: string;
  };
  agentEdit: {
    value: number;
    display: string;
    units: string;
  };
  agentReasoning: string;
  status: "Approved" | "Pending" | "Flagged";
  dashbaordData?: string;
}

interface ForecastTableProps {
  smartSortFilter?: boolean;
  selectedTab?: string;
  onTabChange?: (tab: string) => void;
  totalFlagged?: number;
  totalAll?: number;
  viewLevel?: "sku" | "productLine";
  triageData?: any;
  productLineData?: any;
  onUpdateStatus?: (productLink: string, newStatus: "Submitted" | "Pending") => void;
  baseRoute?: string;
  isDPWorkflow?: boolean;
  customer?: string;
}

export function ForecastTable({
  smartSortFilter = false,
  selectedTab = "all",
  onTabChange,
  totalFlagged = 0,
  totalAll = 0,
  viewLevel = "sku",
  triageData,
  productLineData,
  onUpdateStatus,
  baseRoute = "/forecast-workflow",
  isDPWorkflow = false,
  customer = "default"
}: ForecastTableProps) {
  const forecastData = triageData?.skuList as ForecastItem[] || [];
  const productLineList = productLineData?.productLineList as ProductLineItem[] || [];
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isFeatureEnabled } = useFeatureFlags();

  // For food dist demo, always show units
  const isFoodDist = customer === 'fooddist';

  // Preserve customer parameter in navigation
  const buildNavUrl = (path: string, dataParam?: string) => {
    const customerParam = searchParams.get('customer');
    const params = new URLSearchParams();
    if (dataParam) params.set('data', dataParam);
    if (customerParam) params.set('customer', customerParam);
    const queryString = params.toString();
    return queryString ? `${path}?${queryString}` : path;
  };
  const [selectedReportProduct, setSelectedReportProduct] = useState<string | null>(null);
  const [selectedReportData, setSelectedReportData] = useState<string | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [showNewReport, setShowNewReport] = useState(false);
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [showUnits, setShowUnits] = useState(isFoodDist); // food dist defaults to units
  const [executiveContextFilter, setExecutiveContextFilter] = useState(false);

  const getValidationColor = (failed: number, total: number): "destructive2" | "warning2" | "primary2" => {
    if (failed === 0) return "primary2";
    if (failed >= 3) return "destructive2";
    return "warning2";
  };

  const getValidationColorForStatus = (status: string): "destructive2" | "warning2" | "primary2" => {
    if (status === "Approved" || status === "Submitted") return "primary2";
    if (status === "Pending") return "warning2";
    return "destructive2";
  };

  const getIconsForStatus = (status: string): React.ReactNode => {
    if (status === "Approved" || status === "Submitted") return <CheckCircle className="h-3 w-3 mr-1" />;
    if (status === "Pending") return <Clock className="h-3 w-3 mr-1" />;
    return <TriangleAlert className="h-3 w-3 mr-1" />;
  };

  const getPerformanceColor = (wins: number, total: number): string => {
    const ratio = wins / total;
    if (ratio === 1) return "text-primary"; // 3/3 - green
    if (ratio >= 0.5) return "text-warning"; // 2/3 - orange
    return "text-destructive"; // 1/3 or 0/3 - red
  };

  // Determine which data to use based on view level
  const isProductLineView = viewLevel === "productLine";
  
  // Filter SKU data
  let filteredSkuData = selectedTab === "flagged" 
    ? forecastData.filter(item => item.decision === "Suggested")
    : forecastData;

  if (smartSortFilter) {
    filteredSkuData = filteredSkuData.filter(item => item.smartSortFilter);
  }

  // Filter Product Line data
  let filteredProductLineData = selectedTab === "flagged"
    ? productLineList.filter(item => item.decision === "Suggested")
    : productLineList;

  if (smartSortFilter) {
    filteredProductLineData = filteredProductLineData.filter(item => item.smartSortFilter);
  }

  // Handle sorting
  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
  };

  // Generic sorting function
  const sortData = <T extends ForecastItem | ProductLineItem>(data: T[], column: string | null, direction: "asc" | "desc"): T[] => {
    if (!column) return data;

    return [...data].sort((a, b) => {
      let aValue: any;
      let bValue: any;

      switch (column) {
        case "decision":
          aValue = a.decision === "Autonomous" ? 0 : 1;
          bValue = b.decision === "Autonomous" ? 0 : 1;
          break;
        case "productName":
          aValue = a.productLink.toLowerCase();
          bValue = b.productLink.toLowerCase();
          break;
        case "region":
          aValue = (a as ProductLineItem).region?.toLowerCase() || "";
          bValue = (b as ProductLineItem).region?.toLowerCase() || "";
          break;
        case "skuCount":
          aValue = (a as ProductLineItem).skuCount || 0;
          bValue = (b as ProductLineItem).skuCount || 0;
          break;
        case "historicalPerformance":
          aValue = a.historicalPerformance.wins / a.historicalPerformance.total;
          bValue = b.historicalPerformance.wins / b.historicalPerformance.total;
          break;
        case "failedValidations":
          aValue = a.failedValidations.failed;
          bValue = b.failedValidations.failed;
          break;
        case "flaggedRevenue":
          aValue = a.flaggedRevenue.value;
          bValue = b.flaggedRevenue.value;
          break;
        case "dollarizedVolume":
          aValue = a.dollarizedVolume.value;
          bValue = b.dollarizedVolume.value;
          break;
        case "agentEdit":
          aValue = a.agentEdit.value;
          bValue = b.agentEdit.value;
          break;
        case "status":
          const statusOrder: { [key: string]: number } = { Approved: 0, Submitted: 0, Pending: 1, Flagged: 2 };
          aValue = statusOrder[a.status] ?? 3;
          bValue = statusOrder[b.status] ?? 3;
          break;
        default:
          return 0;
      }

      if (aValue < bValue) return direction === "asc" ? -1 : 1;
      if (aValue > bValue) return direction === "asc" ? 1 : -1;
      return 0;
    });
  };

  // Apply sorting with useMemo
  const sortedSkuData = useMemo(() => {
    return sortData(filteredSkuData, sortColumn, sortDirection);
  }, [filteredSkuData, sortColumn, sortDirection]);

  const sortedProductLineData = useMemo(() => {
    return sortData(filteredProductLineData, sortColumn, sortDirection);
  }, [filteredProductLineData, sortColumn, sortDirection]);

  // Render sort icon
  const renderSortIcon = (column: string) => {
    if (sortColumn !== column) {
      return <ArrowUpDown className="ml-2 h-4 w-4 inline-block opacity-50" />;
    }
    return sortDirection === "asc" 
      ? <ArrowUp className="ml-2 h-4 w-4 inline-block" />
      : <ArrowDown className="ml-2 h-4 w-4 inline-block" />;
  };

  return (
    <>
      {/* Table Controls Row - Tabs and Filters */}
      <div className="flex items-center justify-between mb-4">
        {/* Tabs */}
        {onTabChange && (
          <Tabs value={selectedTab} onValueChange={onTabChange}>
            <TabsList>
              <TabsTrigger value="flagged">
                Items Flagged ({totalFlagged})
              </TabsTrigger>
              <TabsTrigger value="all">
                All Items ({totalAll})
              </TabsTrigger>
            </TabsList>
          </Tabs>
        )}

        {/* Right side controls */}
        <div className="flex items-center gap-6 ml-auto">
          {/* Executive Context Filter */}
          <div className="flex items-center gap-2">
            <Checkbox
              id="executive-context"
              checked={executiveContextFilter}
              onCheckedChange={(checked) => setExecutiveContextFilter(checked === true)}
            />
            <Label htmlFor="executive-context" className="text-sm cursor-pointer">
              Filter by Executive Context
            </Label>
          </div>

          {/* Units/Revenue Toggle */}
          <div className="flex items-center gap-2">
            <Label
              htmlFor="units-toggle"
              className={`text-sm ${!showUnits ? 'font-medium text-foreground' : 'text-muted-foreground'}`}
            >
              Revenue
            </Label>
            <Switch
              id="units-toggle"
              checked={showUnits}
              onCheckedChange={setShowUnits}
            />
            <Label
              htmlFor="units-toggle"
              className={`text-sm ${showUnits ? 'font-medium text-foreground' : 'text-muted-foreground'}`}
            >
              Units
            </Label>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-border">
      <Table className="w-full">
        <TableHeader>
          {isDPWorkflow ? (
            <>
              {/* First header row with parent columns - DP Workflow */}
              <TableRow className="bg-muted h-[32px] border-b">
                <TableHead
                  className="text-foreground text-xs font-semibold w-[70px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("decision")}
                >
                  Decision{renderSortIcon("decision")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold text-center border-r bg-muted"
                  colSpan={2}
                >
                  Forecast Level
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[120px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("historicalPerformance")}
                >
                  Historical Performance{renderSortIcon("historicalPerformance")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[100px] border-l cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("failedValidations")}
                >
                  Failed Validations{renderSortIcon("failedValidations")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[90px] border-l cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("flaggedRevenue")}
                >
                  Flagged Revenue{renderSortIcon("flaggedRevenue")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[100px] bg-muted"
                  rowSpan={2}
                >
                  Customer Forecast
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[90px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("dollarizedVolume")}
                >
                  Forecasted Value{renderSortIcon("dollarizedVolume")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[80px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("agentEdit")}
                >
                  Agent Edit{renderSortIcon("agentEdit")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[180px] bg-muted"
                  rowSpan={2}
                >
                  Agent Reasoning
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[80px] bg-muted"
                  rowSpan={2}
                >
                  Action
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[80px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("status")}
                >
                  Status{renderSortIcon("status")}
                </TableHead>
              </TableRow>
              {/* Second header row with sub-columns - DP Workflow */}
              <TableRow className="bg-muted h-[32px]">
                <TableHead
                  className="text-foreground text-xs w-[120px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  onClick={() => handleSort("productName")}
                >
                  Product{renderSortIcon("productName")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs w-[80px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  onClick={() => handleSort("retailer")}
                >
                  Customer{renderSortIcon("retailer")}
                </TableHead>
              </TableRow>
            </>
          ) : (
            <>
              {/* First header row with parent columns - Dashboard workflow */}
              <TableRow className="bg-muted h-[32px] border-b">
                <TableHead
                  className="text-foreground text-xs font-semibold w-[70px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("decision")}
                >
                  Decision{renderSortIcon("decision")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold text-center border-r bg-muted"
                  colSpan={3}
                >
                  Forecast Level
                </TableHead>
                {isProductLineView && (
                  <>
                    <TableHead
                      className="text-foreground text-xs font-semibold w-[120px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                      rowSpan={2}
                      onClick={() => handleSort("region")}
                    >
                      Region{renderSortIcon("region")}
                    </TableHead>
                    <TableHead
                      className="text-foreground text-xs font-semibold w-[100px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                      rowSpan={2}
                    >
                      SKUs
                    </TableHead>
                  </>
                )}
                <TableHead
                  className="text-foreground text-xs font-semibold w-[120px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("historicalPerformance")}
                >
                  Historical Performance{renderSortIcon("historicalPerformance")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[100px] border-l cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("failedValidations")}
                >
                  Failed Validations{renderSortIcon("failedValidations")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[90px] border-l cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("flaggedRevenue")}
                >
                  Flagged Revenue{renderSortIcon("flaggedRevenue")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[90px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("dollarizedVolume")}
                >
                  Forecasted Value{renderSortIcon("dollarizedVolume")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[80px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("agentEdit")}
                >
                  Agent Edit{renderSortIcon("agentEdit")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[180px] bg-muted"
                  rowSpan={2}
                >
                  Agent Reasoning
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[80px] bg-muted"
                  rowSpan={2}
                >
                  Action
                </TableHead>
                <TableHead
                  className="text-foreground text-xs font-semibold w-[80px] cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  rowSpan={2}
                  onClick={() => handleSort("status")}
                >
                  Status{renderSortIcon("status")}
                </TableHead>
              </TableRow>
              {/* Second header row with sub-columns - Dashboard workflow */}
              <TableRow className="bg-muted h-[32px]">
                <TableHead
                  className="text-foreground text-xs w-[60px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  onClick={() => handleSort("productName")}
                >
                  Product{renderSortIcon("productName")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs w-[50px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  onClick={() => handleSort("site")}
                >
                  Site{renderSortIcon("site")}
                </TableHead>
                <TableHead
                  className="text-foreground text-xs w-[50px] border-r cursor-pointer hover:bg-muted-foreground/20 transition-colors bg-muted"
                  onClick={() => handleSort("retailer")}
                >
                  Customer{renderSortIcon("retailer")}
                </TableHead>
              </TableRow>
            </>
          )}
        </TableHeader>
        <TableBody>
          {isProductLineView ? (
            // Product Line View
            sortedProductLineData.map((item, index) => (
              <TableRow 
                key={`pl-${item.id}-${index}`} 
                className={`hover:bg-gray-100 cursor-pointer ${index % 2 === 1 ? 'bg-slate-50' : 'bg-white'}`}
                onClick={() => {
                  const dataParam = item.dashbaordData || 'default';
                  navigate(buildNavUrl(`${baseRoute}/${item.id}`, dataParam));
                }}
              >
                <TableCell>
                  <Badge variant={item.decision === "Autonomous" ? "secondary" : "outline"}
                  className={`py-1 rounded-[6px] w-[100px] min-w-[100px] justify-center items-center ${item.decision === "Autonomous" ? "text-green-800" : "bg-indigo-100 text-blue-800"}`}>
                    {item.decision}
                  </Badge>
                </TableCell>
                {isDPWorkflow ? (
                  <>
                    {/* Product cell */}
                    <TableCell>
                      <span className="text-sm font-medium text-foreground">
                        {item.productLink}
                      </span>
                    </TableCell>
                    {/* Customer cell */}
                    <TableCell className="border-r">
                      <div className="text-sm font-medium text-foreground">{item.region}</div>
                    </TableCell>
                  </>
                ) : (
                  <>
                    {/* Product cell */}
                    <TableCell>
                      <span className="text-sm font-medium text-foreground">
                        {item.productLink}
                      </span>
                    </TableCell>
                    {/* Site cell */}
                    <TableCell>
                      <div className="text-sm font-medium text-foreground">{item.region}</div>
                    </TableCell>
                    {/* Customer cell */}
                    <TableCell className="border-r">
                      <Badge variant="outline" className="bg-muted/50 text-foreground border-border">
                        {item.region}
                      </Badge>
                    </TableCell>
                  </>
                )}
                <TableCell className="border-l">
                  <div className={`text-base font-semibold mb-1 ${getPerformanceColor(item.historicalPerformance.wins, item.historicalPerformance.total)}`}>
                    {item.historicalPerformance.display}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {item.historicalPerformance.description}
                  </p>
                </TableCell>
                <TableCell className="border-r">
                  <Badge 
                    variant={getValidationColor(item.failedValidations.failed, item.failedValidations.total)}
                  >
                    {item.failedValidations.display}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="text-sm font-medium text-foreground">{showUnits ? item.flaggedRevenue.units : item.flaggedRevenue.display}</div>
                  <p className="text-xs text-muted-foreground">{showUnits ? item.flaggedRevenue.display : item.flaggedRevenue.units}</p>
                </TableCell>
                <TableCell>
                  <div className="text-sm font-medium text-foreground">{showUnits ? item.dollarizedVolume.units : item.dollarizedVolume.display}</div>
                  <p className="text-xs text-muted-foreground">{showUnits ? item.dollarizedVolume.display : item.dollarizedVolume.units}</p>
                </TableCell>
                <TableCell>
                  <div className="text-sm font-medium text-foreground">{showUnits ? item.agentEdit.units : item.agentEdit.display}</div>
                  <p className="text-xs text-muted-foreground">{showUnits ? item.agentEdit.display : item.agentEdit.units}</p>
                </TableCell>
                <TableCell>
                  <p className="text-[13px] text-foreground">{item.agentReasoning}</p>
                </TableCell>
                <TableCell>
                  <Button
                    variant="default"
                    size="sm"
                    className="bg-primary hover:bg-primary/90 text-primary-foreground"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedReportProduct(item.productLink);
                      setShowNewReport(false);
                    }}
                  >
                    View Report
                  </Button>
                </TableCell>
                <TableCell>
                  <Badge
                    variant={getValidationColorForStatus(item.status)}
                  >
                    {getIconsForStatus(item.status)}
                    {item.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          ) : (
            // SKU View (existing)
            sortedSkuData.map((item, index) => (
              <TableRow 
                key={`sku-${item.id}-${index}`} 
                className={`hover:bg-gray-100 cursor-pointer ${index % 2 === 1 ? 'bg-slate-50' : 'bg-white'}`}
                onClick={() => {
                  const dataParam = item.dashbaordData || 'default';
                  navigate(buildNavUrl(`${baseRoute}/${item.id}`, dataParam));
                }}
              >
                <TableCell>
                  <Badge variant={item.decision === "Autonomous" ? "secondary" : "outline"}
                    className={`py-1 rounded-[6px] w-[100px] min-w-[100px] justify-center items-center ${item.decision === "Autonomous" ? "text-green-800" : "bg-indigo-100 text-blue-800"}`}>
                    {item.decision}
                  </Badge>
                </TableCell>
                {isDPWorkflow ? (
                  <>
                    <TableCell>
                      <span className="text-sm font-medium text-foreground">
                        {item.productName}
                      </span>
                    </TableCell>
                    <TableCell className="border-r">
                      <div className="text-sm font-medium text-foreground">{item.retailer}</div>
                      <p className="text-xs text-muted-foreground">{item.site}</p>
                    </TableCell>
                  </>
                ) : (
                  <>
                    {/* Product cell */}
                    <TableCell>
                      <span className="text-sm font-medium text-foreground">
                        {item.productName}
                      </span>
                    </TableCell>
                    {/* Site cell */}
                    <TableCell>
                      <div className="text-sm font-medium text-foreground">{item.site}</div>
                    </TableCell>
                    {/* Customer cell */}
                    <TableCell className="border-r">
                      <div className="text-sm font-medium text-foreground">{item.retailer}</div>
                    </TableCell>
                  </>
                )}
                <TableCell className="border-l">
                  <div className={`text-base font-semibold mb-1 ${getPerformanceColor(item.historicalPerformance.wins, item.historicalPerformance.total)}`}>
                    {item.historicalPerformance.display}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {item.historicalPerformance.description}
                  </p>
                </TableCell>
                <TableCell className="border-r">
                  <Badge 
                    variant={getValidationColor(item.failedValidations.failed, item.failedValidations.total)}
                  >
                    {item.failedValidations.display}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="text-sm font-medium text-foreground">{showUnits ? item.flaggedRevenue.units : item.flaggedRevenue.display}</div>
                  <p className="text-xs text-muted-foreground">{showUnits ? item.flaggedRevenue.display : item.flaggedRevenue.units}</p>
                </TableCell>
                {isDPWorkflow && (
                  <TableCell>
                    {(() => {
                      // Generate customer forecast within 5-15% of dollarized volume
                      const baseValue = item.dollarizedVolume.value;
                      const seed = item.id * 17 + item.productName.length;
                      const isHigher = seed % 2 === 0;
                      const percentage = 5 + (seed % 11); // 5-15%
                      const multiplier = isHigher ? (1 + percentage / 100) : (1 - percentage / 100);
                      const customerForecastValue = Math.round(baseValue * multiplier);
                      // Extract numeric value from units string (e.g., "9,600 cases" -> 9600)
                      const unitsMatch = item.dollarizedVolume.units.match(/[\d,]+/);
                      const unitsValue = unitsMatch ? parseInt(unitsMatch[0].replace(/,/g, '')) : 0;
                      const customerUnitsValue = Math.round(unitsValue * multiplier);
                      const formattedDollars = `$${customerForecastValue.toLocaleString()}`;
                      const formattedUnits = `${customerUnitsValue.toLocaleString()} cases`;
                      return (
                        <>
                          <div className="text-sm font-medium text-foreground">{showUnits ? formattedUnits : formattedDollars}</div>
                          <p className="text-xs text-muted-foreground">{showUnits ? formattedDollars : item.dollarizedVolume.units}</p>
                        </>
                      );
                    })()}
                  </TableCell>
                )}
                <TableCell>
                  <div className="text-sm font-medium text-foreground">{showUnits ? item.dollarizedVolume.units : item.dollarizedVolume.display}</div>
                  <p className="text-xs text-muted-foreground">{showUnits ? item.dollarizedVolume.display : item.dollarizedVolume.units}</p>
                </TableCell>
                <TableCell>
                  <div className="text-sm font-medium text-foreground">{showUnits ? item.agentEdit.units : item.agentEdit.display}</div>
                  <p className="text-xs text-muted-foreground">{showUnits ? item.agentEdit.display : item.agentEdit.units}</p>
                </TableCell>
                <TableCell>
                  <p className="text-[13px] text-foreground">{item.agentReasoning}</p>
                </TableCell>
                <TableCell>
                  {isFeatureEnabled('enableAgentReports') && (
                    <Button
                      variant="default"
                      size="sm"
                      className="bg-primary hover:bg-primary/90 text-primary-foreground"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedReportProduct(item.productLink);
                        setSelectedReportData(item.dashbaordData || null);
                        setSelectedReportId(item.id);
                        setShowNewReport(true);
                      }}
                    >
                      View Report
                    </Button>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={getValidationColorForStatus(item.status)}>
                    {getIconsForStatus(item.status)}
                    {item.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>

    {isFeatureEnabled('enableAgentReports') && (
      <AgentReportPanel
        open={selectedReportProduct !== null}
        onClose={() => {
          setSelectedReportProduct(null);
          setSelectedReportData(null);
          setSelectedReportId(null);
          setShowNewReport(false);
        }}
        productLink={selectedReportProduct}
        dataParam={selectedReportData}
        skuId={selectedReportId}
        onUpdateStatus={onUpdateStatus}
      />
    )}
    </>
  );
}
