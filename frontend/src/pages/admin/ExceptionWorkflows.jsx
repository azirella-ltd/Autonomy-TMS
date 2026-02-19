/**
 * Exception Workflows Admin Page
 *
 * Manage automated exception routing, escalation paths, and SLA configuration
 * for forecast exceptions.
 *
 * Phase 3.3: Exception Management Workflows
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
  Modal,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Switch,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  Plus,
  Pencil,
  Trash2,
  ArrowUpDown,
  Clock,
  ClipboardList,
  Bell,
  Cog,
  Calendar,
} from 'lucide-react';
import { api } from '../../services/api';

const EXCEPTION_TYPES = [
  { value: 'VARIANCE', label: 'Variance' },
  { value: 'TREND_BREAK', label: 'Trend Break' },
  { value: 'SEASONALITY_MISS', label: 'Seasonality Miss' },
  { value: 'OUTLIER', label: 'Outlier' },
  { value: 'BIAS', label: 'Bias' },
  { value: 'MANUAL', label: 'Manual' },
];

const SEVERITY_LEVELS = [
  { value: 'LOW', label: 'Low', color: 'success' },
  { value: 'MEDIUM', label: 'Medium', color: 'warning' },
  { value: 'HIGH', label: 'High', color: 'destructive' },
  { value: 'CRITICAL', label: 'Critical', color: 'destructive' },
];

const NOTIFICATION_CHANNELS = ['email', 'slack', 'teams', 'in_app', 'sms'];

const ExceptionWorkflows = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [stats, setStats] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    code: '',
    description: '',
    exception_types: [],
    severity_levels: [],
    sla_hours: '',
    sla_warning_hours: '',
    is_active: true,
    escalation_levels: [],
    auto_resolve_config: {
      enabled: false,
      conditions: {},
      action: 'resolve',
    },
    initial_assignment: {
      type: 'role',
      role: 'demand_planner',
    },
  });

  useEffect(() => {
    fetchTemplates();
    fetchStats();
  }, []);

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const response = await api.get('/exception-workflows/templates');
      setTemplates(response.data);
    } catch (err) {
      setError('Failed to load workflow templates');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await api.get('/exception-workflows/stats');
      setStats(response.data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const handleOpenDialog = (template = null) => {
    if (template) {
      setEditingTemplate(template);
      setFormData({
        name: template.name,
        code: template.code,
        description: template.description || '',
        exception_types: template.exception_types?.types || [],
        severity_levels: template.severity_levels?.levels || [],
        sla_hours: template.sla_hours || '',
        sla_warning_hours: template.sla_warning_hours || '',
        is_active: template.is_active,
        escalation_levels: template.escalation_levels?.levels || [],
        auto_resolve_config: template.auto_resolve_config || {
          enabled: false,
          conditions: {},
          action: 'resolve',
        },
        initial_assignment: template.initial_assignment || {
          type: 'role',
          role: 'demand_planner',
        },
      });
    } else {
      setEditingTemplate(null);
      setFormData({
        name: '',
        code: '',
        description: '',
        exception_types: [],
        severity_levels: [],
        sla_hours: '',
        sla_warning_hours: '',
        is_active: true,
        escalation_levels: [],
        auto_resolve_config: {
          enabled: false,
          conditions: {},
          action: 'resolve',
        },
        initial_assignment: {
          type: 'role',
          role: 'demand_planner',
        },
      });
    }
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingTemplate(null);
  };

  const handleSave = async () => {
    try {
      const payload = {
        ...formData,
        sla_hours: formData.sla_hours ? parseInt(formData.sla_hours) : null,
        sla_warning_hours: formData.sla_warning_hours ? parseInt(formData.sla_warning_hours) : null,
      };

      if (editingTemplate) {
        await api.put(`/exception-workflows/templates/${editingTemplate.id}`, payload);
      } else {
        await api.post('/exception-workflows/templates', payload);
      }

      fetchTemplates();
      handleCloseDialog();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save template');
    }
  };

  const handleDelete = async (templateId) => {
    if (!window.confirm('Are you sure you want to delete this workflow template?')) {
      return;
    }

    try {
      await api.delete(`/exception-workflows/templates/${templateId}`);
      fetchTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete template');
    }
  };

  const handleAddEscalationLevel = () => {
    const newLevel = {
      level: formData.escalation_levels.length + 1,
      hours_after_creation: 24 * (formData.escalation_levels.length + 1),
      assign_to_role: 'supervisor',
      notification_channels: ['email'],
    };
    setFormData({
      ...formData,
      escalation_levels: [...formData.escalation_levels, newLevel],
    });
  };

  const handleRemoveEscalationLevel = (index) => {
    const newLevels = formData.escalation_levels.filter((_, i) => i !== index);
    newLevels.forEach((level, i) => {
      level.level = i + 1;
    });
    setFormData({
      ...formData,
      escalation_levels: newLevels,
    });
  };

  const handleEscalationChange = (index, field, value) => {
    const newLevels = [...formData.escalation_levels];
    newLevels[index][field] = value;
    setFormData({
      ...formData,
      escalation_levels: newLevels,
    });
  };

  const toggleExceptionType = (type) => {
    const current = formData.exception_types;
    if (current.includes(type)) {
      setFormData({ ...formData, exception_types: current.filter(t => t !== type) });
    } else {
      setFormData({ ...formData, exception_types: [...current, type] });
    }
  };

  const toggleSeverityLevel = (level) => {
    const current = formData.severity_levels;
    if (current.includes(level)) {
      setFormData({ ...formData, severity_levels: current.filter(l => l !== level) });
    } else {
      setFormData({ ...formData, severity_levels: [...current, level] });
    }
  };

  const toggleNotificationChannel = (index, channel) => {
    const level = formData.escalation_levels[index];
    const current = level.notification_channels || [];
    let updated;
    if (current.includes(channel)) {
      updated = current.filter(c => c !== channel);
    } else {
      updated = [...current, channel];
    }
    handleEscalationChange(index, 'notification_channels', updated);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Exception Workflows</h1>
          <p className="text-sm text-muted-foreground">
            Configure automated routing, escalation paths, and SLA for forecast exceptions
          </p>
        </div>
        <Button onClick={() => handleOpenDialog()} leftIcon={<Plus className="h-4 w-4" />}>
          New Workflow
        </Button>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Statistics Cards */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">Total Exceptions</p>
              <p className="text-3xl font-bold">{stats.total_exceptions}</p>
              <p className="text-xs text-muted-foreground">Last 30 days</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">Pending</p>
              <p className="text-3xl font-bold text-amber-600">{stats.pending_exceptions}</p>
              <p className="text-xs text-muted-foreground">Awaiting resolution</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">SLA Compliance</p>
              <p className={`text-3xl font-bold ${stats.sla_compliance_rate >= 90 ? 'text-green-600' : 'text-red-600'}`}>
                {stats.sla_compliance_rate != null ? `${stats.sla_compliance_rate}%` : 'N/A'}
              </p>
              <p className="text-xs text-muted-foreground">On-time resolution</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">Avg Resolution Time</p>
              <p className="text-3xl font-bold">
                {stats.avg_resolution_time_hours != null ? `${stats.avg_resolution_time_hours}h` : 'N/A'}
              </p>
              <p className="text-xs text-muted-foreground">Hours to resolve</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Workflow Templates Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Code</TableHead>
                <TableHead>Exception Types</TableHead>
                <TableHead>Severities</TableHead>
                <TableHead>SLA</TableHead>
                <TableHead>Escalations</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {templates.map((template) => (
                <TableRow key={template.id}>
                  <TableCell>
                    <p className="font-medium">{template.name}</p>
                    {template.description && (
                      <p className="text-xs text-muted-foreground">{template.description}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{template.code}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {template.exception_types?.types?.map((type) => (
                        <Badge key={type} variant="outline">{type}</Badge>
                      )) || <span className="text-muted-foreground">All</span>}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {template.severity_levels?.levels?.map((sev) => (
                        <Badge
                          key={sev}
                          variant={SEVERITY_LEVELS.find(s => s.value === sev)?.color || 'secondary'}
                        >
                          {sev}
                        </Badge>
                      )) || <span className="text-muted-foreground">All</span>}
                    </div>
                  </TableCell>
                  <TableCell>
                    {template.sla_hours ? (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge variant="outline" className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {template.sla_hours}h
                            </Badge>
                          </TooltipTrigger>
                          <TooltipContent>Warning at {template.sla_warning_hours || 'N/A'}h</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ) : <span className="text-muted-foreground">None</span>}
                  </TableCell>
                  <TableCell>
                    {template.escalation_levels?.levels?.length > 0 ? (
                      <Badge variant="outline" className="flex items-center gap-1">
                        <ArrowUpDown className="h-3 w-3" />
                        {template.escalation_levels.levels.length} levels
                      </Badge>
                    ) : <span className="text-muted-foreground">None</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant={template.is_active ? 'success' : 'secondary'}>
                      {template.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => handleOpenDialog(template)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleDelete(template.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {templates.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                    No workflow templates configured. Create one to get started.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Modal
        isOpen={dialogOpen}
        onClose={handleCloseDialog}
        title={editingTemplate ? 'Edit Workflow Template' : 'Create Workflow Template'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog}>Cancel</Button>
            <Button onClick={handleSave}>
              {editingTemplate ? 'Update' : 'Create'}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Name *</Label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Workflow name"
              />
            </div>
            <div>
              <Label>Code *</Label>
              <Input
                value={formData.code}
                onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                disabled={!!editingTemplate}
                placeholder="Unique identifier (e.g., HIGH_PRIORITY)"
              />
            </div>
            <div className="col-span-2">
              <Label>Description</Label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={2}
              />
            </div>
          </div>

          {/* Matching Criteria */}
          <div>
            <h4 className="font-medium mb-2">Matching Criteria</h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Exception Types</Label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {EXCEPTION_TYPES.map((type) => (
                    <Badge
                      key={type.value}
                      variant={formData.exception_types.includes(type.value) ? 'default' : 'outline'}
                      className="cursor-pointer"
                      onClick={() => toggleExceptionType(type.value)}
                    >
                      {type.label}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <Label>Severity Levels</Label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {SEVERITY_LEVELS.map((sev) => (
                    <Badge
                      key={sev.value}
                      variant={formData.severity_levels.includes(sev.value) ? sev.color : 'outline'}
                      className="cursor-pointer"
                      onClick={() => toggleSeverityLevel(sev.value)}
                    >
                      {sev.label}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* SLA Configuration */}
          <div>
            <h4 className="font-medium mb-2">SLA Configuration</h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>SLA Hours</Label>
                <Input
                  type="number"
                  value={formData.sla_hours}
                  onChange={(e) => setFormData({ ...formData, sla_hours: e.target.value })}
                  placeholder="Target resolution time in hours"
                />
              </div>
              <div>
                <Label>Warning Hours</Label>
                <Input
                  type="number"
                  value={formData.sla_warning_hours}
                  onChange={(e) => setFormData({ ...formData, sla_warning_hours: e.target.value })}
                  placeholder="Hours before SLA to trigger warning"
                />
              </div>
            </div>
          </div>

          {/* Escalation Levels */}
          <Accordion type="single" collapsible>
            <AccordionItem value="escalation">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <ArrowUpDown className="h-4 w-4" />
                  Escalation Levels ({formData.escalation_levels.length})
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4">
                  {formData.escalation_levels.map((level, index) => (
                    <div key={index} className="border rounded p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="font-medium">Level {level.level}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveEscalationLevel(index)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <Label>Hours After Creation</Label>
                          <Input
                            type="number"
                            value={level.hours_after_creation}
                            onChange={(e) => handleEscalationChange(index, 'hours_after_creation', parseInt(e.target.value))}
                          />
                        </div>
                        <div>
                          <Label>Assign To Role</Label>
                          <Input
                            value={level.assign_to_role || ''}
                            onChange={(e) => handleEscalationChange(index, 'assign_to_role', e.target.value)}
                          />
                        </div>
                        <div>
                          <Label>Notify Via</Label>
                          <div className="flex flex-wrap gap-1 mt-2">
                            {NOTIFICATION_CHANNELS.map((ch) => (
                              <Badge
                                key={ch}
                                variant={(level.notification_channels || []).includes(ch) ? 'default' : 'outline'}
                                className="cursor-pointer"
                                onClick={() => toggleNotificationChannel(index, ch)}
                              >
                                {ch}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleAddEscalationLevel}
                    leftIcon={<Plus className="h-4 w-4" />}
                  >
                    Add Escalation Level
                  </Button>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          {/* Auto-Resolve */}
          <Accordion type="single" collapsible>
            <AccordionItem value="auto-resolve">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <Cog className="h-4 w-4" />
                  Auto-Resolve Configuration
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={formData.auto_resolve_config?.enabled || false}
                      onCheckedChange={(checked) => setFormData({
                        ...formData,
                        auto_resolve_config: {
                          ...formData.auto_resolve_config,
                          enabled: checked,
                        },
                      })}
                    />
                    <Label>Enable Auto-Resolve</Label>
                  </div>
                  {formData.auto_resolve_config?.enabled && (
                    <div>
                      <Label>Action</Label>
                      <Select
                        value={formData.auto_resolve_config?.action || 'resolve'}
                        onValueChange={(value) => setFormData({
                          ...formData,
                          auto_resolve_config: {
                            ...formData.auto_resolve_config,
                            action: value,
                          },
                        })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="resolve">Resolve</SelectItem>
                          <SelectItem value="defer">Defer</SelectItem>
                          <SelectItem value="suppress">Suppress</SelectItem>
                        </SelectContent>
                      </Select>
                      <Alert variant="info" className="mt-4">
                        Auto-resolution conditions can be configured via API for advanced use cases.
                      </Alert>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          {/* Status */}
          <div className="flex items-center gap-2">
            <Switch
              checked={formData.is_active}
              onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
            />
            <Label>Active</Label>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ExceptionWorkflows;
