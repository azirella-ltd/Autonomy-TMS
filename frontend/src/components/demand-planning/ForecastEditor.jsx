/**
 * Forecast Editor Component
 *
 * Editable table for demand forecast adjustments.
 * Features:
 * - Inline cell editing
 * - Bulk adjustments (percentage, delta)
 * - Adjustment history view
 * - Undo/redo support
 * - Save with reason capture
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Save,
  Undo2,
  Redo2,
  History,
  Percent,
  Plus,
  Filter,
  RefreshCw,
  Check,
  X,
  Pencil,
  MoreVertical,
} from 'lucide-react';

// Autonomy UI Kit imports
import { Button, IconButton, Card, CardContent, Input, Label, Textarea, FormField, Alert, Badge } from '../common';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../common/Table';
import { Spinner } from '../common/Loading';
// NOTE: the original code imported { Select, SelectOption } from the Radix
// wrapper at components/common/Select, but that module only exports
// SelectItem (not SelectOption) and follows a different API (SelectTrigger /
// SelectContent pattern, not e.target.value). The REASON_CODES dropdown in
// the Save dialog is simple enough to use a plain native <select>, so we
// avoid both the missing-export crash and Radix's strict empty-string
// Select.Item check which failed whenever reasonCode was still "".
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
} from '../ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../ui/tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';

import { api } from '../../services/api';

const REASON_CODES = [
  { value: 'promotion', label: 'Promotion' },
  { value: 'seasonal', label: 'Seasonal Adjustment' },
  { value: 'event', label: 'Special Event' },
  { value: 'market_intelligence', label: 'Market Intelligence' },
  { value: 'correction', label: 'Data Correction' },
  { value: 'other', label: 'Other' },
];

const ForecastEditor = ({ configId, onSave }) => {
  // Data state
  const [forecastData, setForecastData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Edit state
  const [editedCells, setEditedCells] = useState({});
  const [selectedCells, setSelectedCells] = useState([]);
  const [editingCell, setEditingCell] = useState(null);
  const [editValue, setEditValue] = useState('');

  // History for undo/redo
  const [history, setHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Dialog state
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const [bulkType, setBulkType] = useState('percentage');
  const [bulkValue, setBulkValue] = useState('');
  const [reasonDialogOpen, setReasonDialogOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState('');
  const [reasonText, setReasonText] = useState('');
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);
  const [cellHistory, setCellHistory] = useState([]);

  // Filter state
  const [productFilter, setProductFilter] = useState('');
  const [siteFilter, setSiteFilter] = useState('');

  // Load forecast data
  const loadForecastData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (configId) params.config_id = configId;

      const response = await api.get('/forecast-adjustments/table', { params });
      setForecastData(response.data);
      setEditedCells({});
      setHistory([]);
      setHistoryIndex(-1);
    } catch (err) {
      setError('Failed to load forecast data');
      console.error('Error loading forecasts:', err);
    } finally {
      setLoading(false);
    }
  }, [configId]);

  useEffect(() => {
    loadForecastData();
  }, [loadForecastData]);

  // Group cells by product and site
  const groupedData = useMemo(() => {
    if (!forecastData?.cells) return {};

    const grouped = {};
    forecastData.cells.forEach(cell => {
      const key = `${cell.product_id}-${cell.site_id}`;
      if (!grouped[key]) {
        grouped[key] = {
          product_id: cell.product_id,
          product_name: cell.product_name,
          site_id: cell.site_id,
          site_name: cell.site_name,
          periods: {}
        };
      }
      grouped[key].periods[cell.period] = cell;
    });

    return grouped;
  }, [forecastData]);

  // Filter rows
  const filteredRows = useMemo(() => {
    return Object.values(groupedData).filter(row => {
      if (productFilter && !row.product_name.toLowerCase().includes(productFilter.toLowerCase())) {
        return false;
      }
      if (siteFilter && !row.site_name.toLowerCase().includes(siteFilter.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [groupedData, productFilter, siteFilter]);

  // Check if there are unsaved changes
  const hasChanges = Object.keys(editedCells).length > 0;

  // Handle cell click to edit
  const handleCellClick = (cell) => {
    setEditingCell(cell.forecast_id);
    setEditValue(editedCells[cell.forecast_id]?.new_value ?? cell.adjusted_forecast);
  };

  // Handle edit value change
  const handleEditChange = (e) => {
    setEditValue(e.target.value);
  };

  // Save cell edit
  const handleEditSave = (cell) => {
    const newValue = parseFloat(editValue);
    if (isNaN(newValue) || newValue < 0) {
      setError('Please enter a valid positive number');
      return;
    }

    // Add to history
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push({
      cellId: cell.forecast_id,
      oldValue: editedCells[cell.forecast_id]?.new_value ?? cell.adjusted_forecast,
      newValue: newValue
    });
    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);

    // Update edited cells
    setEditedCells(prev => ({
      ...prev,
      [cell.forecast_id]: {
        forecast_id: cell.forecast_id,
        original_value: cell.base_forecast,
        new_value: newValue,
        adjustment_type: 'absolute',
        adjustment_value: newValue
      }
    }));

    setEditingCell(null);
    setEditValue('');
  };

  // Cancel edit
  const handleEditCancel = () => {
    setEditingCell(null);
    setEditValue('');
  };

  // Undo
  const handleUndo = () => {
    if (historyIndex < 0) return;

    const item = history[historyIndex];
    setEditedCells(prev => {
      const newCells = { ...prev };
      if (item.oldValue === undefined) {
        delete newCells[item.cellId];
      } else {
        newCells[item.cellId] = {
          ...newCells[item.cellId],
          new_value: item.oldValue
        };
      }
      return newCells;
    });
    setHistoryIndex(historyIndex - 1);
  };

  // Redo
  const handleRedo = () => {
    if (historyIndex >= history.length - 1) return;

    const item = history[historyIndex + 1];
    setEditedCells(prev => ({
      ...prev,
      [item.cellId]: {
        ...prev[item.cellId],
        new_value: item.newValue
      }
    }));
    setHistoryIndex(historyIndex + 1);
  };

  // Open bulk adjustment dialog
  const handleBulkAdjustment = (type) => {
    setBulkType(type);
    setBulkValue('');
    setBulkDialogOpen(true);
  };

  // Apply bulk adjustment
  const handleApplyBulkAdjustment = () => {
    const value = parseFloat(bulkValue);
    if (isNaN(value)) {
      setError('Please enter a valid number');
      return;
    }

    const cellsToAdjust = selectedCells.length > 0
      ? selectedCells
      : forecastData.cells.map(c => c.forecast_id);

    const newEdits = {};
    cellsToAdjust.forEach(cellId => {
      const cell = forecastData.cells.find(c => c.forecast_id === cellId);
      if (!cell) return;

      const currentValue = editedCells[cellId]?.new_value ?? cell.adjusted_forecast;
      let newValue;

      if (bulkType === 'percentage') {
        newValue = currentValue * (1 + value / 100);
      } else if (bulkType === 'delta') {
        newValue = currentValue + value;
      }

      newEdits[cellId] = {
        forecast_id: cellId,
        original_value: cell.base_forecast,
        new_value: Math.max(0, newValue),
        adjustment_type: bulkType,
        adjustment_value: value
      };
    });

    setEditedCells(prev => ({ ...prev, ...newEdits }));
    setBulkDialogOpen(false);
    setSuccess(`Applied ${bulkType} adjustment to ${Object.keys(newEdits).length} cells`);
    setTimeout(() => setSuccess(null), 3000);
  };

  // Save all changes
  const handleSaveAll = () => {
    if (!hasChanges) return;
    setReasonDialogOpen(true);
  };

  // Confirm save with reason
  const handleConfirmSave = async () => {
    setSaving(true);
    setError(null);

    try {
      const adjustments = Object.values(editedCells).map(cell => ({
        forecast_id: cell.forecast_id,
        adjustment_type: cell.adjustment_type,
        adjustment_value: cell.adjustment_value,
        reason_code: reasonCode || null,
        reason_text: reasonText || null
      }));

      if (adjustments.length === 1) {
        await api.post('/forecast-adjustments/', adjustments[0]);
      } else {
        await api.post('/forecast-adjustments/bulk', {
          adjustment_type: 'absolute',
          adjustment_value: 0,
          forecast_ids: adjustments.map(a => a.forecast_id),
          reason_code: reasonCode || null,
          reason_text: reasonText || null
        });
      }

      setSuccess('Changes saved successfully');
      setEditedCells({});
      setHistory([]);
      setHistoryIndex(-1);
      setReasonDialogOpen(false);
      setReasonCode('');
      setReasonText('');

      if (onSave) onSave();

      // Reload data
      await loadForecastData();
    } catch (err) {
      setError('Failed to save changes');
      console.error('Error saving:', err);
    } finally {
      setSaving(false);
    }
  };

  // View cell history
  const handleViewHistory = async (cell) => {
    try {
      const response = await api.get(`/forecast-adjustments/history/${cell.forecast_id}`);
      setCellHistory(response.data);
      setHistoryDialogOpen(true);
    } catch (err) {
      setError('Failed to load adjustment history');
    }
  };

  // Get cell value (edited or original)
  const getCellValue = (cell) => {
    return editedCells[cell.forecast_id]?.new_value ?? cell.adjusted_forecast;
  };

  // Get cell classes based on edit state
  const getCellClasses = (cell) => {
    const isEdited = editedCells[cell.forecast_id] !== undefined;
    const isSelected = selectedCells.includes(cell.forecast_id);

    return [
      'cursor-pointer',
      isEdited ? 'bg-amber-100/50 dark:bg-amber-900/20 font-bold' : '',
      isSelected ? 'bg-blue-100/50 dark:bg-blue-900/20' : '',
      cell.has_adjustments ? 'border-l-4 border-l-amber-500' : '',
    ].filter(Boolean).join(' ');
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div>
        {/* Toolbar */}
        <div className="flex items-center gap-2 mb-4 flex-wrap px-0">
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <IconButton onClick={handleUndo} disabled={historyIndex < 0}>
                    <Undo2 className="h-4 w-4" />
                  </IconButton>
                </span>
              </TooltipTrigger>
              <TooltipContent>Undo (Ctrl+Z)</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <IconButton onClick={handleRedo} disabled={historyIndex >= history.length - 1}>
                    <Redo2 className="h-4 w-4" />
                  </IconButton>
                </span>
              </TooltipTrigger>
              <TooltipContent>Redo (Ctrl+Y)</TooltipContent>
            </Tooltip>
          </div>

          <hr className="h-6 w-px bg-border mx-1" />

          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Percent className="h-4 w-4" />}
              onClick={() => handleBulkAdjustment('percentage')}
            >
              % Adjust
            </Button>
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Plus className="h-4 w-4" />}
              onClick={() => handleBulkAdjustment('delta')}
            >
              +/- Adjust
            </Button>
          </div>

          <hr className="h-6 w-px bg-border mx-1" />

          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Filter by product..."
              value={productFilter}
              onChange={(e) => setProductFilter(e.target.value)}
              className="pl-9 w-44 h-9"
            />
          </div>

          <Input
            placeholder="Filter by site..."
            value={siteFilter}
            onChange={(e) => setSiteFilter(e.target.value)}
            className="w-36 h-9"
          />

          <div className="flex-grow" />

          <Button
            variant="outline"
            leftIcon={<RefreshCw className="h-4 w-4" />}
            onClick={loadForecastData}
            disabled={loading}
          >
            Refresh
          </Button>

          <Button
            leftIcon={<Save className="h-4 w-4" />}
            onClick={handleSaveAll}
            disabled={!hasChanges || saving}
          >
            {saving ? 'Saving...' : `Save ${Object.keys(editedCells).length} Changes`}
          </Button>
        </div>

        {/* Alerts */}
        {error && (
          <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {success && (
          <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}

        {/* Forecast Table */}
        <Card className="overflow-hidden">
          <div className="max-h-[600px] overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur z-10">
                <TableRow>
                  <TableHead className="min-w-[200px]">Product / Site</TableHead>
                  {forecastData?.periods?.map(period => (
                    <TableHead key={period} className="min-w-[80px] text-right">
                      {period}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRows.map((row) => (
                  <TableRow key={`${row.product_id}-${row.site_id}`}>
                    <TableCell>
                      <p className="font-medium text-sm">{row.product_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {row.site_name}
                      </p>
                    </TableCell>
                    {forecastData?.periods?.map(period => {
                      const cell = row.periods[period];
                      if (!cell) return <TableCell key={period} />;

                      const isEditing = editingCell === cell.forecast_id;
                      const value = getCellValue(cell);

                      return (
                        <TableCell
                          key={period}
                          className={getCellClasses(cell)}
                          onClick={() => !isEditing && handleCellClick(cell)}
                        >
                          {isEditing ? (
                            <div className="flex items-center gap-1">
                              <Input
                                type="number"
                                value={editValue}
                                onChange={handleEditChange}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleEditSave(cell);
                                  if (e.key === 'Escape') handleEditCancel();
                                }}
                                autoFocus
                                className="w-16 h-7 text-right px-1"
                              />
                              <IconButton size="icon" className="h-6 w-6" onClick={() => handleEditSave(cell)}>
                                <Check className="h-3 w-3" />
                              </IconButton>
                              <IconButton size="icon" className="h-6 w-6" onClick={handleEditCancel}>
                                <X className="h-3 w-3" />
                              </IconButton>
                            </div>
                          ) : (
                            <div className="flex items-center justify-end gap-1">
                              <span className="text-sm">
                                {Math.round(value)}
                              </span>
                              {cell.has_adjustments && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Pencil className="h-3.5 w-3.5 text-amber-500" />
                                  </TooltipTrigger>
                                  <TooltipContent>Has adjustments</TooltipContent>
                                </Tooltip>
                              )}
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <IconButton
                                    size="icon"
                                    className="h-6 w-6 opacity-50 hover:opacity-100"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <MoreVertical className="h-3 w-3" />
                                  </IconButton>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem onClick={() => handleCellClick(cell)}>
                                    <Pencil className="h-4 w-4 mr-2" />
                                    Edit Value
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={() => handleViewHistory(cell)}>
                                    <History className="h-4 w-4 mr-2" />
                                    View History
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          )}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>

        {/* Bulk Adjustment Dialog */}
        <Dialog open={bulkDialogOpen} onOpenChange={setBulkDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {bulkType === 'percentage' ? 'Percentage Adjustment' : 'Add/Subtract Value'}
              </DialogTitle>
            </DialogHeader>
            <div className="py-4">
              <p className="text-sm text-muted-foreground mb-4">
                {selectedCells.length > 0
                  ? `Apply to ${selectedCells.length} selected cells`
                  : 'Apply to all visible cells'}
              </p>
              <FormField
                label={bulkType === 'percentage' ? 'Percentage (e.g., 10 for +10%)' : 'Value to add/subtract'}
                helperText={bulkType === 'percentage'
                  ? 'Enter positive value to increase, negative to decrease'
                  : 'Enter positive value to add, negative to subtract'}
              >
                <div className="relative">
                  <Input
                    type="number"
                    value={bulkValue}
                    onChange={(e) => setBulkValue(e.target.value)}
                    className={bulkType === 'percentage' ? 'pr-8' : ''}
                  />
                  {bulkType === 'percentage' && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">%</span>
                  )}
                </div>
              </FormField>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setBulkDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleApplyBulkAdjustment}>
                Apply
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Save Reason Dialog */}
        <Dialog open={reasonDialogOpen} onOpenChange={setReasonDialogOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Save Forecast Adjustments</DialogTitle>
            </DialogHeader>
            <div className="py-4">
              <p className="text-sm text-muted-foreground mb-4">
                You are saving {Object.keys(editedCells).length} adjustment(s).
                Please provide a reason for these changes.
              </p>
              <div className="space-y-4">
                <FormField label="Reason Code">
                  <select
                    value={reasonCode}
                    onChange={(e) => setReasonCode(e.target.value)}
                    className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="" disabled>Select a reason code</option>
                    {REASON_CODES.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Additional Notes (optional)">
                  <Textarea
                    rows={3}
                    value={reasonText}
                    onChange={(e) => setReasonText(e.target.value)}
                    placeholder="Describe the reason for these adjustments..."
                  />
                </FormField>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReasonDialogOpen(false)}>Cancel</Button>
              <Button
                onClick={handleConfirmSave}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* History Dialog */}
        <Dialog open={historyDialogOpen} onOpenChange={setHistoryDialogOpen}>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>Adjustment History</DialogTitle>
            </DialogHeader>
            <div className="py-4">
              {cellHistory.length === 0 ? (
                <p className="text-muted-foreground">No adjustment history found.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-right">Original</TableHead>
                      <TableHead className="text-right">Adjustment</TableHead>
                      <TableHead className="text-right">New Value</TableHead>
                      <TableHead>Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cellHistory.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          {new Date(item.created_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" size="sm">{item.adjustment_type}</Badge>
                        </TableCell>
                        <TableCell className="text-right">{item.original_value}</TableCell>
                        <TableCell className="text-right">
                          {item.adjustment_type === 'percentage'
                            ? `${item.adjustment_value}%`
                            : item.adjustment_value}
                        </TableCell>
                        <TableCell className="text-right">{item.new_value}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {item.reason_code && <Badge variant="outline" size="sm">{item.reason_code}</Badge>}
                            <span className="text-sm">{item.reason_text}</span>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setHistoryDialogOpen(false)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  );
};

export default ForecastEditor;
