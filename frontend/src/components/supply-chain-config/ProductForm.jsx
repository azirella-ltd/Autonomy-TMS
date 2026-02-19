import React, { useState } from 'react';
import {
  Button,
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
import { Plus, Pencil, Trash2, Save, X } from 'lucide-react';
import RangeInput from './RangeInput';

const ProductForm = ({ products = [], onAdd, onUpdate, onDelete, loading = false, navigationButtons = null }) => {
  const [openDialog, setOpenDialog] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    unit_cost_range: { min: 0, max: 100 },
  });
  const [errors, setErrors] = useState({});

  const handleOpenDialog = (product = null) => {
    if (product) {
      setEditingProduct(product);
      setFormData({
        name: product.name,
        description: product.description || '',
        unit_cost_range: product.unit_cost_range || { min: 0, max: 100 },
      });
    } else {
      setEditingProduct(null);
      setFormData({
        name: '',
        description: '',
        unit_cost_range: { min: 0, max: 100 },
      });
    }
    setErrors({});
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingProduct(null);
    setFormData({
      name: '',
      description: '',
      unit_cost_range: { min: 0, max: 100 },
    });
    setErrors({});
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (
      !formData.unit_cost_range ||
      formData.unit_cost_range.min === undefined ||
      formData.unit_cost_range.max === undefined ||
      formData.unit_cost_range.min < 0 ||
      formData.unit_cost_range.max < formData.unit_cost_range.min
    ) {
      newErrors.unit_cost_range = 'Invalid cost range';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    const productData = {
      name: formData.name.trim(),
      description: formData.description.trim(),
      unit_cost_range: formData.unit_cost_range,
    };

    if (editingProduct) {
      onUpdate(editingProduct.id, productData);
    } else {
      onAdd(productData);
    }

    handleCloseDialog();
  };

  const handleDelete = (productId) => {
    if (window.confirm('Are you sure you want to delete this product? This action cannot be undone.')) {
      onDelete(productId);
    }
  };

  const handleChange = (name, value) => {
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleRangeChange = (field, value) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Products</h3>
        <div className="flex gap-2">
          <Button
            onClick={() => handleOpenDialog()}
            disabled={loading}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Product
          </Button>
          {navigationButtons}
        </div>
      </div>

      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Unit Cost Range</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {products.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center">
                  No products added yet. Click "Add Product" to get started.
                </TableCell>
              </TableRow>
            ) : (
              products.map((product) => (
                <TableRow key={product.id}>
                  <TableCell>{product.name}</TableCell>
                  <TableCell>
                    {product.description || (
                      <span className="text-muted-foreground">No description</span>
                    )}
                  </TableCell>
                  <TableCell>
                    ${product.unit_cost_range?.min?.toFixed(2)} - ${product.unit_cost_range?.max?.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenDialog(product)}
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
                            className="text-destructive"
                            onClick={() => handleDelete(product.id)}
                            disabled={loading}
                          >
                            <Trash2 className="h-4 w-4" />
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
      </div>

      <Modal
        isOpen={openDialog}
        onClose={handleCloseDialog}
        title={editingProduct ? 'Edit Product' : 'Add New Product'}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog} disabled={loading} leftIcon={<X className="h-4 w-4" />}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={loading}
              leftIcon={editingProduct ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            >
              {editingProduct ? 'Update' : 'Add'} Product
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="product-name">Product Name</Label>
            <Input
              id="product-name"
              value={formData.name}
              onChange={(e) => handleChange('name', e.target.value)}
              disabled={loading}
              className={errors.name ? 'border-destructive' : ''}
            />
            {errors.name && <p className="text-sm text-destructive mt-1">{errors.name}</p>}
          </div>

          <div>
            <Label htmlFor="product-description">Description</Label>
            <Textarea
              id="product-description"
              value={formData.description}
              onChange={(e) => handleChange('description', e.target.value)}
              disabled={loading}
              rows={2}
            />
          </div>

          <div>
            <RangeInput
              label="Unit Cost Range ($)"
              value={formData.unit_cost_range}
              onChange={(value) => handleRangeChange('unit_cost_range', value)}
              min={0}
              max={10000}
              step={0.01}
              disabled={loading}
            />
            {errors.unit_cost_range && (
              <p className="text-sm text-destructive mt-1">{errors.unit_cost_range}</p>
            )}
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default ProductForm;
