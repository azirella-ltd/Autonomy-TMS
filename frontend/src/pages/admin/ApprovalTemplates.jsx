/**
 * Approval Templates Management Page
 *
 * Allows administrators to configure multi-level approval workflows
 * for different entity types (PO, TO, MO, SUPPLY_PLAN, etc.)
 */

import React, { useState, useEffect, useCallback } from 'react';
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
  Switch,
  Spinner,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  Plus,
  Pencil,
  Trash2,
  CheckCircle,
  XCircle,
  ArrowUp,
  ArrowDown,
  Copy,
} from 'lucide-react';
import { api } from '../../services/api';

const ENTITY_TYPES = [
  { value: 'PO', label: 'Purchase Order' },
  { value: 'TO', label: 'Transfer Order' },
  { value: 'MO', label: 'Maintenance Order' },
  { value: 'SUPPLY_PLAN', label: 'Supply Plan' },
  { value: 'MPS', label: 'Master Production Schedule' },
  { value: 'MRP', label: 'Material Requirements Plan' },
  { value: 'FORECAST', label: 'Forecast Adjustment' },
];

const APPROVAL_TYPES = [
  { value: 'any', label: 'Any One Approver', description: 'First approval advances the workflow' },
  { value: 'all', label: 'All Approvers', description: 'All approvers must approve to advance' },
];

const ApprovalTemplates = () => {
  const [templates, setTemplates] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [templateToDelete, setTemplateToDelete] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    entity_type: 'PO',
    levels: [{ level: 1, approvers: [], type: 'any' }],
    conditions: { min_value: null, categories: [] },
    is_active: true,
  });

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get('/approval-templates/');
      setTemplates(response.data || []);
    } catch (err) {
      setError('Failed to load approval templates');
      console.error('Error loading templates:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const response = await api.get('/users/');
      setUsers(response.data?.users || response.data || []);
    } catch (err) {
      console.error('Error loading users:', err);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
    loadUsers();
  }, [loadTemplates, loadUsers]);

  const handleCreateNew = () => {
    setEditingTemplate(null);
    setFormData({
      name: '',
      description: '',
      entity_type: 'PO',
      levels: [{ level: 1, approvers: [], type: 'any' }],
      conditions: { min_value: null, categories: [] },
      is_active: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (template) => {
    setEditingTemplate(template);
    setFormData({
      name: template.name,
      description: template.description || '',
      entity_type: template.entity_type,
      levels: template.levels || [{ level: 1, approvers: [], type: 'any' }],
      conditions: template.conditions || { min_value: null, categories: [] },
      is_active: template.is_active,
    });
    setDialogOpen(true);
  };

  const handleDuplicate = (template) => {
    setEditingTemplate(null);
    setFormData({
      name: `${template.name} (Copy)`,
      description: template.description || '',
      entity_type: template.entity_type,
      levels: JSON.parse(JSON.stringify(template.levels || [{ level: 1, approvers: [], type: 'any' }])),
      conditions: JSON.parse(JSON.stringify(template.conditions || { min_value: null, categories: [] })),
      is_active: false,
    });
    setDialogOpen(true);
  };

  const handleDeleteClick = (template) => {
    setTemplateToDelete(template);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!templateToDelete) return;

    try {
      await api.delete(`/approval-templates/${templateToDelete.id}`);
      setSuccess('Template deleted successfully');
      setDeleteDialogOpen(false);
      setTemplateToDelete(null);
      loadTemplates();
    } catch (err) {
      setError('Failed to delete template');
      console.error('Error deleting template:', err);
    }
  };

  const handleSave = async () => {
    try {
      const payload = {
        ...formData,
        levels: formData.levels.map((level, idx) => ({
          ...level,
          level: idx + 1,
        })),
      };

      if (editingTemplate) {
        await api.put(`/approval-templates/${editingTemplate.id}`, payload);
        setSuccess('Template updated successfully');
      } else {
        await api.post('/approval-templates/', payload);
        setSuccess('Template created successfully');
      }

      setDialogOpen(false);
      loadTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save template');
      console.error('Error saving template:', err);
    }
  };

  const handleToggleActive = async (template) => {
    try {
      await api.put(`/approval-templates/${template.id}`, {
        ...template,
        is_active: !template.is_active,
      });
      loadTemplates();
    } catch (err) {
      setError('Failed to update template status');
    }
  };

  const addApprovalLevel = () => {
    setFormData(prev => ({
      ...prev,
      levels: [
        ...prev.levels,
        { level: prev.levels.length + 1, approvers: [], type: 'any' },
      ],
    }));
  };

  const removeApprovalLevel = (index) => {
    if (formData.levels.length <= 1) return;
    setFormData(prev => ({
      ...prev,
      levels: prev.levels.filter((_, i) => i !== index),
    }));
  };

  const moveLevel = (index, direction) => {
    const newLevels = [...formData.levels];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= newLevels.length) return;

    [newLevels[index], newLevels[targetIndex]] = [newLevels[targetIndex], newLevels[index]];
    setFormData(prev => ({ ...prev, levels: newLevels }));
  };

  const updateLevel = (index, field, value) => {
    setFormData(prev => ({
      ...prev,
      levels: prev.levels.map((level, i) =>
        i === index ? { ...level, [field]: value } : level
      ),
    }));
  };

  const toggleApprover = (levelIndex, userId) => {
    const level = formData.levels[levelIndex];
    const current = level.approvers || [];
    if (current.includes(userId)) {
      updateLevel(levelIndex, 'approvers', current.filter(id => id !== userId));
    } else {
      updateLevel(levelIndex, 'approvers', [...current, userId]);
    }
  };

  const getUserName = (userId) => {
    const user = users.find(u => u.id === userId);
    return user ? `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.email : `User ${userId}`;
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-6 flex justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Approval Templates</h1>
          <p className="text-sm text-muted-foreground">
            Configure multi-level approval workflows for orders and plans
          </p>
        </div>
        <Button onClick={handleCreateNew} leftIcon={<Plus className="h-4 w-4" />}>
          Create Template
        </Button>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Entity Type</TableHead>
                <TableHead>Levels</TableHead>
                <TableHead>Conditions</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {templates.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    No approval templates configured. Create one to get started.
                  </TableCell>
                </TableRow>
              ) : (
                templates.map((template) => (
                  <TableRow key={template.id}>
                    <TableCell>
                      <p className="font-medium">{template.name}</p>
                      {template.description && (
                        <p className="text-xs text-muted-foreground">{template.description}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {ENTITY_TYPES.find(e => e.value === template.entity_type)?.label || template.entity_type}
                      </Badge>
                    </TableCell>
                    <TableCell>{template.levels?.length || 0} level(s)</TableCell>
                    <TableCell>
                      {template.conditions?.min_value ? (
                        <Badge variant="outline">Min: ${template.conditions.min_value.toLocaleString()}</Badge>
                      ) : (
                        <span className="text-muted-foreground text-sm">No conditions</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={template.is_active ? 'success' : 'secondary'}
                        className="cursor-pointer flex items-center gap-1 w-fit"
                        onClick={() => handleToggleActive(template)}
                      >
                        {template.is_active ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                        {template.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button variant="ghost" size="sm" onClick={() => handleEdit(template)}>
                                <Pencil className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Edit</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button variant="ghost" size="sm" onClick={() => handleDuplicate(template)}>
                                <Copy className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Duplicate</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button variant="ghost" size="sm" onClick={() => handleDeleteClick(template)}>
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Delete</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Modal
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editingTemplate ? 'Edit Approval Template' : 'Create Approval Template'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={handleSave}
              disabled={!formData.name || formData.levels.some(l => l.approvers?.length === 0)}
            >
              {editingTemplate ? 'Update' : 'Create'}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <div>
            <Label>Template Name *</Label>
            <Input
              value={formData.name}
              onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g., High-Value PO Approval"
            />
          </div>

          <div>
            <Label>Description</Label>
            <Textarea
              value={formData.description}
              onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
              rows={2}
            />
          </div>

          <div>
            <Label>Entity Type</Label>
            <Select
              value={formData.entity_type}
              onValueChange={(value) => setFormData(prev => ({ ...prev, entity_type: value }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ENTITY_TYPES.map(type => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <hr />

          <div>
            <h4 className="font-medium mb-2">Approval Levels</h4>
            <p className="text-sm text-muted-foreground mb-4">
              Configure the sequence of approvals. Each level must be completed before the next.
            </p>

            <div className="space-y-4">
              {formData.levels.map((level, index) => (
                <Card key={index} className="border">
                  <CardContent className="pt-4">
                    <div className="flex justify-between items-center mb-4">
                      <span className="font-medium">Level {index + 1}</span>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => moveLevel(index, 'up')}
                          disabled={index === 0}
                        >
                          <ArrowUp className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => moveLevel(index, 'down')}
                          disabled={index === formData.levels.length - 1}
                        >
                          <ArrowDown className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeApprovalLevel(index)}
                          disabled={formData.levels.length <= 1}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>

                    <div className="mb-4">
                      <Label>Approvers</Label>
                      <div className="flex flex-wrap gap-2 mt-2 p-2 border rounded min-h-[60px]">
                        {users.map(user => (
                          <Badge
                            key={user.id}
                            variant={(level.approvers || []).includes(user.id) ? 'default' : 'outline'}
                            className="cursor-pointer"
                            onClick={() => toggleApprover(index, user.id)}
                          >
                            {`${user.first_name || ''} ${user.last_name || ''}`.trim() || user.email}
                          </Badge>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        Selected: {(level.approvers || []).map(id => getUserName(id)).join(', ') || 'None'}
                      </p>
                    </div>

                    <div>
                      <Label>Approval Type</Label>
                      <Select
                        value={level.type || 'any'}
                        onValueChange={(value) => updateLevel(index, 'type', value)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {APPROVAL_TYPES.map(type => (
                            <SelectItem key={type.value} value={type.value}>
                              {type.label} - {type.description}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={addApprovalLevel}
              className="mt-4"
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Add Approval Level
            </Button>
          </div>

          <hr />

          <div>
            <h4 className="font-medium mb-2">Conditions (Optional)</h4>
            <p className="text-sm text-muted-foreground mb-4">
              Define when this template should be triggered
            </p>

            <div>
              <Label>Minimum Value ($)</Label>
              <Input
                type="number"
                value={formData.conditions?.min_value || ''}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  conditions: {
                    ...prev.conditions,
                    min_value: e.target.value ? parseFloat(e.target.value) : null
                  }
                }))}
                placeholder="e.g., 10000"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Template applies when order value exceeds this amount
              </p>
            </div>
          </div>

          <hr />

          <div className="flex items-center gap-2">
            <Switch
              checked={formData.is_active}
              onCheckedChange={(checked) => setFormData(prev => ({ ...prev, is_active: checked }))}
            />
            <Label>Template Active</Label>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <Modal
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        title="Delete Template"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteConfirm}>Delete</Button>
          </div>
        }
      >
        <p>
          Are you sure you want to delete "{templateToDelete?.name}"? This action cannot be undone.
        </p>
      </Modal>
    </div>
  );
};

export default ApprovalTemplates;
