import React, { useMemo, useState } from 'react';
import {
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
import { Plus, Trash2, Pencil } from 'lucide-react';

const MarketManager = ({
  navigationButtons = null,
  markets = [],
  loading = false,
  onAdd,
  onUpdate,
  onDelete,
}) => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingMarket, setEditingMarket] = useState(null);
  const [formValues, setFormValues] = useState({ name: '', description: '' });
  const [errors, setErrors] = useState({});

  const sortedMarkets = useMemo(
    () => [...markets].sort((a, b) => a.name.localeCompare(b.name)),
    [markets]
  );

  const handleOpenDialog = (market = null) => {
    setEditingMarket(market);
    setFormValues({
      name: market?.name || '',
      description: market?.description || '',
    });
    setErrors({});
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingMarket(null);
  };

  const validate = () => {
    const nextErrors = {};
    if (!formValues.name.trim()) {
      nextErrors.name = 'Market name is required';
    }
    if (
      !editingMarket &&
      sortedMarkets.some(
        (market) => market.name.toLowerCase() === formValues.name.trim().toLowerCase()
      )
    ) {
      nextErrors.name = 'A market with this name already exists';
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) {
      return;
    }

    const payload = {
      name: formValues.name.trim(),
      description: formValues.description.trim() || null,
    };

    if (editingMarket) {
      await onUpdate?.(editingMarket.id, payload);
    } else {
      await onAdd?.(payload);
    }

    handleCloseDialog();
  };

  const handleDelete = async (marketId) => {
    if (!onDelete) {
      return;
    }
    const confirmed = window.confirm(
      'Are you sure you want to delete this market? Market demands for this market will also be removed.'
    );
    if (confirmed) {
      await onDelete(marketId);
    }
  };

  return (
    <Card variant="outline">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Markets</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Define the downstream markets that items can be sold into.
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
                    Add
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Add Market</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {navigationButtons}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {sortedMarkets.length === 0 ? (
          <p className="text-muted-foreground">
            No markets defined yet. Click the add button to create one.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedMarkets.map((market) => (
                <TableRow key={market.id}>
                  <TableCell>{market.name}</TableCell>
                  <TableCell>{market.description || '—'}</TableCell>
                  <TableCell className="text-right">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenDialog(market)}
                            disabled={loading}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Edit</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(market.id)}
                            disabled={loading}
                            className="text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Delete</TooltipContent>
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
        title={editingMarket ? 'Edit Market' : 'Add Market'}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={loading}>
              {editingMarket ? 'Save Changes' : 'Add Market'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="market-name">Name</Label>
            <Input
              id="market-name"
              value={formValues.name}
              onChange={(event) =>
                setFormValues((prev) => ({ ...prev, name: event.target.value }))
              }
              className={errors.name ? 'border-destructive' : ''}
            />
            {errors.name && (
              <p className="text-sm text-destructive mt-1">{errors.name}</p>
            )}
          </div>
          <div>
            <Label htmlFor="market-description">Description</Label>
            <Textarea
              id="market-description"
              value={formValues.description}
              onChange={(event) =>
                setFormValues((prev) => ({ ...prev, description: event.target.value }))
              }
              rows={3}
            />
          </div>
        </div>
      </Modal>
    </Card>
  );
};

export default MarketManager;
