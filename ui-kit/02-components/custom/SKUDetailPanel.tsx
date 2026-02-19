import { useEffect, useState, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ArrowLeft, AlertCircle, CheckCircle2, Pencil, Trash2, Info } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useCustomerData } from "@/hooks/useCustomerData";

// Default fallback SKU data structure for loading state
const defaultSkuData = {
  productName: "Loading...",
  skuDetails: { hierarchy: "", partSite: "", details: "", partSiteCustomer: "", touchLevel: { timesOutperformed: 0, totalCycles: 1 } },
  businessMetrics: { revenueTarget: { display: "" }, decisionQualityScore: { display: "" }, actualRevenueForecast: { display: "", calculation: "" }, flaggedRevenue: "", flaggedUnits: "" },
  validationChecks: { failed: 0, passed: 0 },
  notes: [],
  historicalPerformance: { display: "", trend: "" },
  metadata: { region: "", retailer: "" }
};
interface SKUDetailPanelProps {
  onBack?: () => void;
  showBackButton?: boolean;
  data?: string; // Deprecated: now reads from useCustomerData
  dataSource?: string; // Deprecated: now reads from useCustomerData
  isDPWorkflow?: boolean;
  isValidationDetail?: boolean;
  customerAlignmentFlags?: Array<{
    month: string;
    customerValue: number;
    agentValue: number;
    deviation: number;
  }>;
  historicalSpikeFlags?: Array<{
    month: string;
    weekValue: number;
    average: number;
    deviation: number;
  }>;
  customerForecastAlignmentThreshold?: number;
  historicalSpikeThreshold?: number;
  validationFailedCount?: number;
  validationPassedCount?: number;
  onViewReport?: () => void;
  showViewReportButton?: boolean;
}
export function SKUDetailPanel({
  onBack,
  showBackButton = true,
  data: _deprecatedData, // No longer used, kept for backward compatibility
  dataSource: _deprecatedDataSource, // No longer used
  isDPWorkflow = false,
  isValidationDetail = false,
  customerAlignmentFlags = [],
  historicalSpikeFlags = [],
  customerForecastAlignmentThreshold = 0.30,
  historicalSpikeThreshold = 0.50,
  validationFailedCount,
  validationPassedCount,
  onViewReport,
  showViewReportButton = false
}: SKUDetailPanelProps) {
  const navigate = useNavigate();
  const {
    id
  } = useParams();
  const {
    toast
  } = useToast();

  // Use consolidated customer data hook
  const { currentSkuPanel, productId, isLoading } = useCustomerData();
  const skuData = currentSkuPanel || defaultSkuData;

  // Compute validation counts - handle missing summary fields by counting from checks array
  const validationCounts = useMemo(() => {
    const vc = skuData?.validationChecks;
    if (!vc) return { failed: 0, passed: 0 };

    // If summary fields exist, use them
    if (typeof vc.failed === 'number' && typeof vc.passed === 'number') {
      return { failed: vc.failed, passed: vc.passed };
    }

    // Otherwise compute from checks array
    const checks = vc.checks || [];
    const failed = checks.filter((c: any) => c.status === 'Failed').length;
    const passed = checks.length - failed;
    return { failed, passed };
  }, [skuData]);

  const [note, setNote] = useState("");
  const [isNoteDialogOpen, setIsNoteDialogOpen] = useState(false);
  const [editingNote, setEditingNote] = useState<{
    index: number;
    author: string;
    timestamp: string;
    content: string;
  } | null>(null);
  const [noteContent, setNoteContent] = useState("");

  // Initialize notes from loaded data or sessionStorage
  const [savedNotes, setSavedNotes] = useState<Array<{
    author: string;
    timestamp: string;
    content: string;
  }>>([]);

  // Sync notes when SKU data loads
  useEffect(() => {
    if (productId && skuData?.notes) {
      const storageKey = `sku-notes-${productId}`;
      const storedNotes = sessionStorage.getItem(storageKey);
      if (storedNotes) {
        setSavedNotes(JSON.parse(storedNotes));
      } else {
        setSavedNotes(skuData.notes.map((n: any) => ({
          author: n.author,
          timestamp: n.timestamp,
          content: n.content
        })));
      }
    }
  }, [productId, skuData]);

  // Save notes to sessionStorage whenever they change
  useEffect(() => {
    if (productId && savedNotes.length > 0) {
      const storageKey = `sku-notes-${productId}`;
      sessionStorage.setItem(storageKey, JSON.stringify(savedNotes));
    }
  }, [savedNotes, productId]);
  const handleEditNote = (index: number, note: {
    author: string;
    timestamp: string;
    content: string;
  }) => {
    setEditingNote({
      index,
      ...note
    });
    setNoteContent(note.content);
    setIsNoteDialogOpen(true);
  };
  const handleDeleteNote = (index: number) => {
    setSavedNotes(savedNotes.filter((_, i) => i !== index));
    toast({
      title: "Note deleted",
      description: "The note has been successfully removed."
    });
  };
  const handleSaveNoteFromDialog = () => {
    if (editingNote) {
      setSavedNotes(savedNotes.map((note, i) => i === editingNote.index ? {
        ...note,
        content: noteContent
      } : note));
      toast({
        title: "Note updated",
        description: "Your note has been successfully updated."
      });
    }
    setIsNoteDialogOpen(false);
    setNoteContent("");
    setEditingNote(null);
  };
  const handleSaveNote = () => {
    if (note.trim()) {
      // Use July 3rd, 2025 with current time of day
      const julyDate = new Date('2025-07-03T' + new Date().toTimeString().substring(0, 8));
      setSavedNotes([...savedNotes, {
        author: "User",
        timestamp: julyDate.toLocaleString('en-US', {
          month: '2-digit',
          day: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          hour12: true
        }),
        content: note
      }]);
      setNote("");
      toast({
        title: "Note added",
        description: "Your note has been successfully added."
      });
    }
  };
  return <div className="w-80 border-r border-border bg-background flex flex-col max-h-full">

      <div className="m-3 mt-4">
        <h3 className="font-semibold text-lg text-foreground">{skuData.productName} – {skuData.metadata?.region || ''} – {skuData.metadata?.retailer || ''}</h3>
      </div>

      <div className="overflow-y-auto border border-border rounded-sm m-3">
        {/* SKU Details */}
        <div className="bg-muted">
          <h4 className="text-sm font-semibold p-2 border-b border-border text-foreground">SKU Details</h4>
          <div className="space-y-2 text-sm bg-card p-4">
            <div>
              <span className="text-muted-foreground text-xs">Hierarchy</span>
              <p className="font-medium text-foreground">{skuData.skuDetails.hierarchy}</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Part - Site</span>
              <p className="font-medium text-foreground">{skuData.skuDetails.partSiteCustomer}</p>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="bg-muted">
          <h4 className="text-sm font-semibold p-2 border-y border-border text-foreground">Details</h4>
          <div className="space-y-2 text-sm bg-card p-4">
            <div>
              <span className="text-muted-foreground text-xs">Vendor Name</span>
              <p className="font-medium text-foreground">Pacific Beverage Co.</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Vendor Number</span>
              <p className="font-medium text-foreground">482917</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Pick Up Location</span>
              <p className="font-medium text-foreground">Seattle Distribution Center - WA</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Description</span>
              <p className="font-medium text-foreground">{skuData.skuDetails.details}</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Total Lead Time</span>
              <p className="font-medium text-foreground">14 days</p>
            </div>
          </div>
        </div>

        {/* Historical Performance */}
        <div className="bg-muted">
          <h4 className="text-sm font-semibold p-2 border-y border-border text-foreground">Historical Performance</h4>
          <div className="space-y-2 text-sm bg-card p-4">
            <Badge variant={skuData.skuDetails.touchLevel.timesOutperformed >= skuData.skuDetails.touchLevel.totalCycles / 2 ? "primary2" : "warning2"}>
              <span className="text-center">Outperforms baseline {skuData.skuDetails.touchLevel.timesOutperformed}/{skuData.skuDetails.touchLevel.totalCycles} times</span>
            </Badge>
          </div>
        </div>

        {/* Business Metrics */}
        <div className="bg-muted">
          <h4 className="text-sm font-semibold p-2 border-y border-border text-foreground">Business Metrics</h4>
          <div className="space-y-2 text-sm bg-card p-4">
            <div>
              <span className="text-muted-foreground text-xs">Revenue Target</span>
              <p className="font-medium text-foreground">{skuData.businessMetrics.revenueTarget.display}</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Decision Quality Score</span>
              <div className="flex items-center gap-2">
                <span className="text-lg font-semibold text-primary">{skuData.businessMetrics.decisionQualityScore.display}</span>
              </div>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Dollarized Volume</span>
              <p className="font-medium text-foreground">{skuData.businessMetrics.actualRevenueForecast.display}</p>
              <p className="text-xs text-muted-foreground">{skuData.businessMetrics.actualRevenueForecast.calculation}</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">Flagged Revenue</span>
              <p className="font-medium text-destructive">{(skuData.businessMetrics as any).flaggedRevenue?.display || '-'}</p>
              <p className="text-xs text-muted-foreground">{(skuData.businessMetrics as any).flaggedRevenue?.units || '-'}</p>
            </div>
          </div>
        </div>

        {/* Validation Checks */}
        <div className="bg-muted">
          <h4 className="text-sm font-semibold p-2 border-y border-border text-foreground">Validation Checks</h4>
          <div className="space-y-2 text-sm bg-card p-4">
            {/* Conditional validation counts based on context */}
            <div className="flex gap-2 mb-3">
              <Badge variant="destructive2" className="mr-2">
                <AlertCircle className="h-3 w-3 mr-1" />
                {validationFailedCount !== undefined
                  ? validationFailedCount
                  : isDPWorkflow
                    ? validationCounts.failed + (customerAlignmentFlags.length > 0 ? 1 : 0) + (historicalSpikeFlags.length > 0 ? 1 : 0)
                    : validationCounts.failed
                } Failed
              </Badge>
              <Badge variant="primary2">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                {validationPassedCount !== undefined
                  ? validationPassedCount
                  : isDPWorkflow
                    ? validationCounts.passed + (customerAlignmentFlags.length === 0 ? 1 : 0) + (historicalSpikeFlags.length === 0 ? 1 : 0)
                    : validationCounts.passed
                } Passed
              </Badge>
            </div>

            {/* Customer Forecast Alignment Check */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  
                </TooltipTrigger>
                <TooltipContent side="left" className="max-w-sm">
                  <div className="space-y-2">
                    {customerAlignmentFlags.length > 0 ? <>
                        <p className="font-medium text-xs">Flagged Periods:</p>
                        {customerAlignmentFlags.map((flag, idx) => <div key={idx} className="text-xs space-y-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
                            <p><strong>Period:</strong> {flag.month}</p>
                            <p><strong>Customer:</strong> {flag.customerValue.toLocaleString()} units</p>
                            <p><strong>Autonomy:</strong> {flag.agentValue.toLocaleString()} units</p>
                            <p><strong>Deviation:</strong> {flag.deviation.toFixed(1)}%</p>
                          </div>)}
                      </> : <p className="text-xs">All future periods show customer forecast values within {(customerForecastAlignmentThreshold * 100).toFixed(0)}% of Autonomy's agent-recommended forecast.</p>}
                    <p className="text-xs text-muted-foreground mt-2 pt-2 border-t border-border">
                      Threshold: {(customerForecastAlignmentThreshold * 100).toFixed(0)}% deviation
                    </p>
                  </div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Historical Spike Detection */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  
                </TooltipTrigger>
                <TooltipContent side="left" className="max-w-sm">
                  <div className="space-y-2">
                    {historicalSpikeFlags.length > 0 ? <>
                        <p className="font-medium text-xs">Detected Spikes:</p>
                        {historicalSpikeFlags.map((flag, idx) => <div key={idx} className="text-xs space-y-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
                            <p><strong>Week:</strong> {flag.month}</p>
                            <p><strong>Actual:</strong> {flag.weekValue.toLocaleString()} units</p>
                            <p><strong>6-Week Avg:</strong> {Math.round(flag.average).toLocaleString()} units</p>
                            <p><strong>Deviation:</strong> +{flag.deviation.toFixed(1)}%</p>
                          </div>)}
                      </> : <p className="text-xs">Last 6 weeks of historical actuals show no spikes exceeding {(historicalSpikeThreshold * 100).toFixed(0)}% from the average.</p>}
                    <p className="text-xs text-muted-foreground mt-2 pt-2 border-t border-border">
                      Threshold: +{(historicalSpikeThreshold * 100).toFixed(0)}% from 6-week average
                    </p>
                  </div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {!showViewReportButton && (
              <Button variant="outline" size="sm" className="w-full h-8 text-xs mt-3" onClick={() => navigate(`/validation-detail/${id || '1'}?data=${productId}`)}>
                Check All Validations
              </Button>
            )}
          </div>
        </div>

        {/* Agent Recommendation - Only shown in workflow mode */}
        {showViewReportButton && (
          <div className="bg-muted">
            <h4 className="text-sm font-semibold p-2 border-y border-border text-foreground">Agent Recommendation</h4>
            <div className="space-y-2 text-sm bg-card p-4">
              <p className="text-xs text-muted-foreground mb-3">
                View the AI agent's detailed analysis and forecast recommendation for this SKU.
              </p>
              <Button 
                size="sm" 
                className="w-full h-8 text-xs"
                onClick={onViewReport}
              >
                View Report
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Notes Section */}
      <div className="border-t border-border p-4 bg-background">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-foreground">Notes ({savedNotes.length})</h4>
        </div>

        {savedNotes.length > 0 && <div className="mb-3 space-y-2 max-h-100 overflow-y-auto">
            {savedNotes.map((savedNote, index) => <div key={index} className="text-xs bg-muted p-2 rounded relative group">
                <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleEditNote(index, savedNote)}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive hover:text-destructive" onClick={() => handleDeleteNote(index)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
                <p className="text-muted-foreground pr-16">By {savedNote.author} | {savedNote.timestamp}</p>
                <p className="mt-1 text-foreground">{savedNote.content}</p>
              </div>)}
          </div>}

        <Textarea placeholder="Add a note..." value={note} onChange={e => setNote(e.target.value)} className="min-h-[80px] text-sm mb-2 bg-card" />
        <Button onClick={handleSaveNote} size="sm" className="w-full">
          Save Note
        </Button>
      </div>

      {/* Edit Note Dialog */}
      <Dialog open={isNoteDialogOpen} onOpenChange={setIsNoteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Note</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Textarea value={noteContent} onChange={e => setNoteContent(e.target.value)} placeholder="Edit your note..." className="min-h-[100px]" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
            setIsNoteDialogOpen(false);
            setNoteContent("");
            setEditingNote(null);
          }}>
              Cancel
            </Button>
            <Button onClick={handleSaveNoteFromDialog}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>;
}