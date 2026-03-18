import React, { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Modal,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import { Plus, Trash2, Pencil, Building2 } from 'lucide-react';

/**
 * VendorManager — AWS SC DM compliant step for managing external supply sources.
 *
 * Vendors are TradingPartner records (tpartner_type='vendor') representing
 * external suppliers that deliver raw materials or components into the first
 * internal site. They are NOT Sites — they are outside the company's authority
 * boundary. Each vendor record maps to an inbound lane from the vendor into
 * the first internal site.
 *
 * API: vendors are persisted as Site rows with is_external=true, tpartner_type='vendor'
 * during the Phase 1–3 migration period. The wizard creates them via the Sites API.
 */
const VendorManager = ({
  navigationButtons = null,
  vendors = [],
  loading = false,
  onAdd,
  onUpdate,
  onDelete,
}) => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [formValues, setFormValues] = useState({
    name: '',
    description: '',
    lead_time_days: '',
  });
  const [errors, setErrors] = useState({});

  const sortedVendors = useMemo(
    () => [...vendors].sort((a, b) => a.name.localeCompare(b.name)),
    [vendors]
  );

  const handleOpenDialog = (vendor = null) => {
    setEditingVendor(vendor);
    setFormValues({
      name: vendor?.name || '',
      description: vendor?.description || '',
      lead_time_days: vendor?.lead_time_days != null ? String(vendor.lead_time_days) : '',
    });
    setErrors({});
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingVendor(null);
  };

  const validate = () => {
    const nextErrors = {};
    if (!formValues.name.trim()) {
      nextErrors.name = 'Vendor name is required';
    }
    if (
      !editingVendor &&
      sortedVendors.some(
        (v) => v.name.toLowerCase() === formValues.name.trim().toLowerCase()
      )
    ) {
      nextErrors.name = 'A vendor with this name already exists';
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    // AWS SC DM: vendor = is_external site with tpartner_type='vendor'
    const payload = {
      name: formValues.name.trim(),
      description: formValues.description.trim() || null,
      type: 'vendor',
      master_type: 'vendor',
      is_external: true,
      tpartner_type: 'vendor',
    };
    if (formValues.lead_time_days !== '') {
      const parsed = Number(formValues.lead_time_days);
      if (!Number.isNaN(parsed)) payload.lead_time_days = parsed;
    }

    if (editingVendor) {
      await onUpdate?.(editingVendor.id, payload);
    } else {
      await onAdd?.(payload);
    }
    handleCloseDialog();
  };

  const handleDelete = async (vendorId) => {
    if (!onDelete) return;
    if (
      window.confirm(
        'Delete this vendor? Any inbound transportation lanes connected to this vendor will also be removed.'
      )
    ) {
      await onDelete(vendorId);
    }
  };

  return (
    <Card variant="outline">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Vendors (External Suppliers)</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Add the external suppliers that deliver materials or components into your supply chain.
              Vendors are outside your company's authority boundary (AWS SC: TradingPartner with tpartner_type=vendor).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleOpenDialog()}
                    disabled={loading}
                    leftIcon={<Plus className="h-4 w-4" />}
                  >
                    Add Vendor
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Add an external supplier</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {navigationButtons}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {sortedVendors.length === 0 ? (
          <Alert variant="info">
            No vendors defined yet. Click "Add Vendor" to add an external supplier.
            Vendors represent the upstream boundary of your supply network — where raw materials
            or purchased components enter.
          </Alert>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Vendor Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Default Lead Time</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedVendors.map((vendor) => (
                <TableRow key={vendor.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-blue-600" />
                      <span className="font-medium">{vendor.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {vendor.description || '—'}
                  </TableCell>
                  <TableCell>
                    {vendor.lead_time_days != null ? `${vendor.lead_time_days}d` : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenDialog(vendor)}
                            disabled={loading}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Edit vendor</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(vendor.id)}
                            disabled={loading}
                            className="text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Delete vendor</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <Modal
        isOpen={dialogOpen}
        onClose={handleCloseDialog}
        title={editingVendor ? 'Edit Vendor' : 'Add Vendor'}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={loading}>
              {editingVendor ? 'Save Changes' : 'Add Vendor'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="vendor-name">Vendor Name</Label>
            <Input
              id="vendor-name"
              value={formValues.name}
              onChange={(e) => setFormValues((prev) => ({ ...prev, name: e.target.value }))}
              className={errors.name ? 'border-destructive' : ''}
              placeholder="e.g., Acme Ingredients Ltd."
            />
            {errors.name && (
              <p className="text-sm text-destructive mt-1">{errors.name}</p>
            )}
          </div>
          <div>
            <Label htmlFor="vendor-description">Description</Label>
            <Textarea
              id="vendor-description"
              value={formValues.description}
              onChange={(e) =>
                setFormValues((prev) => ({ ...prev, description: e.target.value }))
              }
              rows={2}
              placeholder="What does this vendor supply?"
            />
          </div>
          <div>
            <Label htmlFor="vendor-lead-time">Default Lead Time (days)</Label>
            <Input
              id="vendor-lead-time"
              type="number"
              min="0"
              value={formValues.lead_time_days}
              onChange={(e) =>
                setFormValues((prev) => ({ ...prev, lead_time_days: e.target.value }))
              }
              placeholder="e.g., 14"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Typical days from purchase order to receipt at your first internal site.
            </p>
          </div>
        </div>
      </Modal>
    </Card>
  );
};

export default VendorManager;
