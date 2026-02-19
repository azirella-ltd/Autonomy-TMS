import { useState, useMemo } from 'react';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Modal,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import { Plus, Pencil, Trash2, GitBranch } from 'lucide-react';

/**
 * BOMForm - Bill of Materials definition for manufacturer sites (AWS SC DM compliant)
 *
 * Displays a hierarchical view of products and their component BOMs.
 * Only manufacturer sites need BOMs defined.
 *
 * Data Structure in Site.attributes:
 * {
 *   "bill_of_materials": {
 *     "<produced_product_id>": {
 *       "<component_product_id>": quantity,
 *       ...
 *     }
 *   }
 * }
 */
const BOMForm = ({
  products = [],
  sites = [],
  onUpdateSite,
  loading = false,
  navigationButtons = null,
  // Backward compatibility aliases (deprecated)
  items = null,
  nodes = null,
  onUpdateNode = null,
}) => {
  // Use products/sites if provided, fall back to items/nodes for backward compat
  const productList = products.length > 0 ? products : (items || []);
  const siteList = sites.length > 0 ? sites : (nodes || []);
  const handleUpdateSite = onUpdateSite || onUpdateNode;
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingSite, setEditingSite] = useState(null);
  const [editingProduct, setEditingProduct] = useState(null);
  const [formData, setFormData] = useState({
    componentId: '',
    quantity: 1,
  });

  // Get manufacturer sites only (AWS SC DM: sites replaces nodes)
  const manufacturerSites = useMemo(() => {
    return siteList.filter((site) => {
      const masterType = (site.master_type || '').toLowerCase();
      return masterType === 'manufacturer';
    });
  }, [siteList]);

  // Parse BOM data from node attributes
  const getBOM = (node) => {
    const attrs = node.attributes || {};
    return attrs.bill_of_materials || {};
  };

  // Get product name by ID
  const getProductName = (productId) => {
    const product = productList.find((p) => p.id === parseInt(productId));
    return product ? product.name : `Product ${productId}`;
  };

  // Get BOM components for a product at a node
  const getComponents = (node, productId) => {
    const bom = getBOM(node);
    const productBOM = bom[productId] || {};
    return Object.entries(productBOM).map(([componentId, quantity]) => ({
      componentId: parseInt(componentId),
      componentName: getProductName(componentId),
      quantity,
    }));
  };

  // Calculate BOM hierarchy depth
  const calculateBOMDepth = (productId, visitedSet = new Set()) => {
    if (visitedSet.has(productId)) return 0; // Circular reference prevention
    visitedSet.add(productId);

    let maxDepth = 0;
    manufacturerSites.forEach((site) => {
      const bom = getBOM(site);
      const productBOM = bom[productId] || {};
      Object.keys(productBOM).forEach((componentId) => {
        const depth = 1 + calculateBOMDepth(componentId, new Set(visitedSet));
        maxDepth = Math.max(maxDepth, depth);
      });
    });

    return maxDepth;
  };

  // Get products sorted by BOM hierarchy (FG at top, raw materials at bottom)
  const sortedProducts = useMemo(() => {
    return [...productList].sort((a, b) => {
      const depthA = calculateBOMDepth(String(a.id));
      const depthB = calculateBOMDepth(String(b.id));
      return depthB - depthA; // Higher depth (more levels below) = earlier in list
    });
  }, [productList, calculateBOMDepth]);

  // Open dialog to add/edit component
  const handleOpenDialog = (site, productId, component = null) => {
    setEditingSite(site);
    setEditingProduct(productId);
    if (component) {
      setFormData({
        componentId: String(component.componentId),
        quantity: component.quantity,
      });
    } else {
      setFormData({
        componentId: '',
        quantity: 1,
      });
    }
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingSite(null);
    setEditingProduct(null);
    setFormData({ componentId: '', quantity: 1 });
  };

  const handleFormChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  // Save BOM component
  const handleSave = () => {
    if (!editingSite || !editingProduct || !formData.componentId) return;

    const attrs = { ...(editingSite.attributes || {}) };
    const bom = { ...(attrs.bill_of_materials || {}) };
    const productBOM = { ...(bom[editingProduct] || {}) };

    // Add or update component
    productBOM[String(formData.componentId)] = formData.quantity;
    bom[editingProduct] = productBOM;
    attrs.bill_of_materials = bom;

    // Update site (AWS SC DM compliant)
    handleUpdateSite(editingSite.id, { attributes: attrs });
    handleCloseDialog();
  };

  // Delete BOM component
  const handleDeleteComponent = (site, productId, componentId) => {
    const attrs = { ...(site.attributes || {}) };
    const bom = { ...(attrs.bill_of_materials || {}) };
    const productBOM = { ...(bom[productId] || {}) };

    delete productBOM[String(componentId)];

    if (Object.keys(productBOM).length === 0) {
      delete bom[productId];
    } else {
      bom[productId] = productBOM;
    }

    attrs.bill_of_materials = bom;
    handleUpdateSite(site.id, { attributes: attrs });
  };

  // Get available components (exclude the product itself and avoid circular refs)
  const getAvailableComponents = (productId) => {
    return productList.filter((product) => String(product.id) !== String(productId));
  };

  // Check if product has BOM defined at any manufacturer
  const hasBOM = (productId) => {
    return manufacturerSites.some((site) => {
      const bom = getBOM(site);
      return bom[productId] && Object.keys(bom[productId]).length > 0;
    });
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-lg font-semibold">Bill of Materials (BOM)</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Define component requirements for products manufactured at each site
          </p>
        </div>
        <div className="flex gap-2">{navigationButtons}</div>
      </div>

      {manufacturerSites.length === 0 && (
        <Alert variant="info" className="mb-4">
          No manufacturer sites defined. Add sites with master type "Manufacturer" to define BOMs.
        </Alert>
      )}

      {productList.length === 0 && (
        <Alert variant="warning" className="mb-4">
          No products defined. Add products first before defining BOMs.
        </Alert>
      )}

      {manufacturerSites.length > 0 && productList.length > 0 && (
        <div>
          <p className="text-sm text-muted-foreground mb-4">
            Products are ordered by hierarchy: Finished goods at top, components below
          </p>

          <Accordion type="multiple" defaultValue={sortedProducts.filter(p => calculateBOMDepth(String(p.id)) > 0).map(p => String(p.id))}>
            {sortedProducts.map((product) => {
              const bomDepth = calculateBOMDepth(String(product.id));

              return (
                <AccordionItem key={product.id} value={String(product.id)}>
                  <AccordionTrigger className="hover:no-underline">
                    <div className="flex items-center gap-3 w-full pr-4">
                      <GitBranch className="h-5 w-5 text-primary" />
                      <div className="flex-1 text-left">
                        <p className="font-medium">{product.name}</p>
                        {product.description && (
                          <p className="text-xs text-muted-foreground">{product.description}</p>
                        )}
                      </div>
                      {hasBOM(String(product.id)) ? (
                        <Badge variant="outline">
                          {bomDepth} level{bomDepth !== 1 ? 's' : ''}
                        </Badge>
                      ) : (
                        <Badge variant="secondary">No BOM</Badge>
                      )}
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="pt-2">
                      {manufacturerSites.map((site) => {
                        const components = getComponents(site, String(product.id));

                        return (
                          <Card key={site.id} variant="outline" className="mb-4">
                            <CardHeader className="pb-2">
                              <div className="flex justify-between items-center">
                                <CardTitle className="text-sm font-medium">
                                  Manufactured at: {site.name}
                                  <Badge variant="secondary" className="ml-2">
                                    {site.dag_type || site.type}
                                  </Badge>
                                </CardTitle>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleOpenDialog(site, String(product.id))}
                                  disabled={loading}
                                  leftIcon={<Plus className="h-4 w-4" />}
                                >
                                  Add Component
                                </Button>
                              </div>
                            </CardHeader>
                            <CardContent>
                              {components.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                  No components defined. Click "Add Component" to define BOM.
                                </p>
                              ) : (
                                <Table>
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead>Component</TableHead>
                                      <TableHead className="text-right">Quantity Required</TableHead>
                                      <TableHead className="text-right">Actions</TableHead>
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {components.map((component) => (
                                      <TableRow key={component.componentId}>
                                        <TableCell>{component.componentName}</TableCell>
                                        <TableCell className="text-right">
                                          <span className="font-medium">{component.quantity}x</span>
                                        </TableCell>
                                        <TableCell className="text-right">
                                          <TooltipProvider>
                                            <Tooltip>
                                              <TooltipTrigger asChild>
                                                <Button
                                                  variant="ghost"
                                                  size="sm"
                                                  onClick={() =>
                                                    handleOpenDialog(site, String(product.id), component)
                                                  }
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
                                                  onClick={() =>
                                                    handleDeleteComponent(
                                                      site,
                                                      String(product.id),
                                                      component.componentId
                                                    )
                                                  }
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
                                    ))}
                                  </TableBody>
                                </Table>
                              )}
                            </CardContent>
                          </Card>
                        );
                      })}

                      {manufacturerSites.length === 0 && (
                        <p className="text-sm text-muted-foreground">
                          No manufacturer sites available for this product.
                        </p>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        </div>
      )}

      {/* Add/Edit Component Dialog */}
      <Modal
        isOpen={dialogOpen}
        onClose={handleCloseDialog}
        title={formData.componentId ? 'Edit Component' : 'Add Component'}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog} disabled={loading}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={loading || !formData.componentId || formData.quantity <= 0}
            >
              Save
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label>Component Product</Label>
            <Select
              value={formData.componentId}
              onValueChange={(value) => handleFormChange('componentId', value)}
              disabled={loading}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a component" />
              </SelectTrigger>
              <SelectContent>
                {getAvailableComponents(editingProduct).map((product) => (
                  <SelectItem key={product.id} value={String(product.id)}>
                    {product.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Quantity Required</Label>
            <Input
              type="number"
              value={formData.quantity}
              onChange={(e) => handleFormChange('quantity', parseFloat(e.target.value) || 1)}
              disabled={loading}
              min={0.01}
              step={0.01}
            />
            <p className="text-xs text-muted-foreground mt-1">
              How many units of this component are needed to produce 1 unit of the parent product
            </p>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default BOMForm;
