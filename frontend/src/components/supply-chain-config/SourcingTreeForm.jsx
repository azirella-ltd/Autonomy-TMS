import { useState, useMemo, useCallback } from 'react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import {
  Plus,
  Trash2,
  Network,
  Package,
  Factory,
  Save,
  TrendingUp,
  LayoutGrid,
} from 'lucide-react';

/**
 * SourcingTreeForm - Smart sourcing tree that follows DAG structure
 *
 * Builds a hierarchical sourcing tree starting from Market Demand + FG Product,
 * following the supply chain DAG, and handling BOM transitions at manufacturers.
 */
const SourcingTreeForm = ({
  products = [],
  sites = [],
  lanes = [],
  markets = [],
  productSiteConfigs = [],
  onAdd,
  onUpdate,
  onDelete,
  loading = false,
  navigationButtons = null,
  // Backward compatibility alias (deprecated)
  items = null,
}) => {
  // Use products if provided, fall back to items for backward compat
  const productList = products.length > 0 ? products : (items || []);
  const [sourcingTrees, setSourcingTrees] = useState([]);
  const [selectedMarket, setSelectedMarket] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('');
  const [expectedDemand, setExpectedDemand] = useState(100);
  const [pathSiteSelections, setPathSiteSelections] = useState({});

  const marketDemandSites = useMemo(() => {
    return sites.filter((site) => {
      const masterType = (site.master_type || '').toLowerCase();
      return masterType === 'market_demand';
    });
  }, [sites]);

  const getBOM = useCallback(
    (site, productId) => {
      const attrs = site.attributes || {};
      const bom = attrs.bill_of_materials || {};
      const productBOM = bom[String(productId)] || {};
      return Object.entries(productBOM)
        .map(([componentId, quantity]) => ({
          componentId: parseInt(componentId),
          component: productList.find((p) => p.id === parseInt(componentId)),
          quantity,
        }))
        .filter((entry) => entry.component);
    },
    [productList]
  );

  const isManufacturer = useCallback((site) => {
    const masterType = (site.master_type || '').toLowerCase();
    return masterType === 'manufacturer';
  }, []);

  const getExistingConfig = useCallback(
    (productId, siteId) => {
      return productSiteConfigs.find(
        (config) => config.product_id === productId && config.site_id === siteId
      );
    },
    [productSiteConfigs]
  );

  const calculateDAGLayer = useCallback(
    (siteId, visited = new Set()) => {
      if (visited.has(siteId)) return Infinity;
      visited.add(siteId);

      const site = sites.find((s) => s.id === siteId);
      if (!site) return Infinity;

      const masterType = (site.master_type || '').toLowerCase();
      if (masterType === 'market_demand') return 0;
      if (masterType === 'market_supply') return Infinity;

      const downstreamLanes = lanes.filter((lane) => lane.from_site_id === siteId);
      if (downstreamLanes.length === 0) return Infinity;

      const downstreamLayers = downstreamLanes.map((lane) =>
        calculateDAGLayer(lane.to_site_id, new Set(visited))
      );

      const minLayer = Math.min(...downstreamLayers);
      return minLayer === Infinity ? Infinity : minLayer + 1;
    },
    [sites, lanes]
  );

  const getSitesAtLayer = useCallback(
    (layer) => {
      return sites
        .filter((site) => {
          const siteLayer = calculateDAGLayer(site.id);
          return siteLayer === layer;
        })
        .filter((site) => {
          const masterType = (site.master_type || '').toLowerCase();
          return masterType !== 'market_demand' && masterType !== 'market_supply';
        });
    },
    [sites, calculateDAGLayer]
  );

  const handleStartConfiguration = () => {
    if (!selectedMarket || !selectedProduct) return;

    const marketSite = marketDemandSites.find((s) => s.id === parseInt(selectedMarket));
    const product = productList.find((p) => p.id === parseInt(selectedProduct));

    if (marketSite && product) {
      const newTree = {
        id: Date.now(),
        marketSiteId: marketSite.id,
        marketSite: marketSite,
        productId: product.id,
        product: product,
        expectedDemand: expectedDemand,
        paths: [],
      };

      setSourcingTrees([...sourcingTrees, newTree]);
      setSelectedMarket('');
      setSelectedProduct('');
      setExpectedDemand(100);
    }
  };

  const handleAddPath = (treeId, priority = 0) => {
    setSourcingTrees((trees) =>
      trees.map((tree) => {
        if (tree.id !== treeId) return tree;

        const newPath = {
          id: Date.now(),
          priority: priority,
          layers: [],
        };

        return {
          ...tree,
          paths: [...tree.paths, newPath],
        };
      })
    );
  };

  const handleAddSiteToPath = (treeId, pathId, siteId, productId, config) => {
    setSourcingTrees((trees) =>
      trees.map((tree) => {
        if (tree.id !== treeId) return tree;

        return {
          ...tree,
          paths: tree.paths.map((path) => {
            if (path.id !== pathId) return path;

            const site = sites.find((s) => s.id === siteId);
            const product = productList.find((p) => p.id === productId);

            const newLayer = {
              id: Date.now(),
              siteId: siteId,
              site: site,
              productId: productId,
              product: product,
              config: config || {
                initialInventory: 0,
                targetInventory: 10,
                holdingCost: 1.0,
                backlogCost: 2.0,
              },
              componentConfigs: [],
            };

            return {
              ...path,
              layers: [...path.layers, newLayer],
            };
          }),
        };
      })
    );
  };

  const handleAddComponentConfig = (treeId, pathId, layerId, componentId, config) => {
    setSourcingTrees((trees) =>
      trees.map((tree) => {
        if (tree.id !== treeId) return tree;

        return {
          ...tree,
          paths: tree.paths.map((path) => {
            if (path.id !== pathId) return path;

            return {
              ...path,
              layers: path.layers.map((layer) => {
                if (layer.id !== layerId) return layer;

                const component = productList.find((p) => p.id === componentId);
                const componentConfig = {
                  id: Date.now(),
                  componentId: componentId,
                  component: component,
                  config: config || {
                    initialInventory: 0,
                    targetInventory: 10,
                    holdingCost: 0.5,
                    backlogCost: 1.0,
                  },
                };

                return {
                  ...layer,
                  componentConfigs: [...layer.componentConfigs, componentConfig],
                };
              }),
            };
          }),
        };
      })
    );
  };

  const handleDeleteTree = (treeId) => {
    setSourcingTrees((trees) => trees.filter((t) => t.id !== treeId));
  };

  const handleDeletePath = (treeId, pathId) => {
    setSourcingTrees((trees) =>
      trees.map((tree) => {
        if (tree.id !== treeId) return tree;
        return {
          ...tree,
          paths: tree.paths.filter((p) => p.id !== pathId),
        };
      })
    );
  };

  const handleDeleteLayer = (treeId, pathId, layerId) => {
    setSourcingTrees((trees) =>
      trees.map((tree) => {
        if (tree.id !== treeId) return tree;
        return {
          ...tree,
          paths: tree.paths.map((path) => {
            if (path.id !== pathId) return path;
            return {
              ...path,
              layers: path.layers.filter((l) => l.id !== layerId),
            };
          }),
        };
      })
    );
  };

  const handleSaveAll = async () => {
    try {
      const configsToCreate = [];

      sourcingTrees.forEach((tree) => {
        tree.paths.forEach((path) => {
          path.layers.forEach((layer) => {
            const existingConfig = getExistingConfig(layer.productId, layer.siteId);

            const configData = {
              product_id: layer.productId,
              site_id: layer.siteId,
              initial_inventory_range: {
                min: layer.config.initialInventory,
                max: layer.config.initialInventory,
              },
              inventory_target_range: {
                min: layer.config.targetInventory,
                max: layer.config.targetInventory,
              },
              holding_cost_range: {
                min: layer.config.holdingCost,
                max: layer.config.holdingCost,
              },
              backlog_cost_range: {
                min: layer.config.backlogCost,
                max: layer.config.backlogCost,
              },
              selling_price_range: { min: 10.0, max: 10.0 },
            };

            if (existingConfig) {
              configsToCreate.push({ type: 'update', id: existingConfig.id, data: configData });
            } else {
              configsToCreate.push({ type: 'create', data: configData });
            }

            layer.componentConfigs.forEach((compConfig) => {
              const existingCompConfig = getExistingConfig(compConfig.componentId, layer.siteId);

              const compConfigData = {
                product_id: compConfig.componentId,
                site_id: layer.siteId,
                initial_inventory_range: {
                  min: compConfig.config.initialInventory,
                  max: compConfig.config.initialInventory,
                },
                inventory_target_range: {
                  min: compConfig.config.targetInventory,
                  max: compConfig.config.targetInventory,
                },
                holding_cost_range: {
                  min: compConfig.config.holdingCost,
                  max: compConfig.config.holdingCost,
                },
                backlog_cost_range: {
                  min: compConfig.config.backlogCost,
                  max: compConfig.config.backlogCost,
                },
                selling_price_range: { min: 5.0, max: 5.0 },
              };

              if (existingCompConfig) {
                configsToCreate.push({ type: 'update', id: existingCompConfig.id, data: compConfigData });
              } else {
                configsToCreate.push({ type: 'create', data: compConfigData });
              }
            });
          });
        });
      });

      for (const config of configsToCreate) {
        if (config.type === 'create') {
          await onAdd(config.data);
        } else if (config.type === 'update') {
          await onUpdate(config.id, config.data);
        }
      }

      console.log('Saved configurations:', configsToCreate);
    } catch (error) {
      console.error('Error saving configurations:', error);
    }
  };

  const renderSiteSelector = (tree, path) => {
    const currentLayer = path.layers.length;
    const availableSites = getSitesAtLayer(currentLayer + 1);

    const pathKey = `${tree.id}-${path.id}`;
    const pathState = pathSiteSelections[pathKey] || {
      selectedSite: '',
      inventoryConfig: {
        initialInventory: 0,
        targetInventory: 10,
        holdingCost: 1.0,
        backlogCost: 2.0,
      },
    };

    const updatePathState = (updates) => {
      setPathSiteSelections((prev) => ({
        ...prev,
        [pathKey]: { ...pathState, ...updates },
      }));
    };

    const lastLayer = path.layers[path.layers.length - 1];
    let currentProduct = tree.product;

    if (lastLayer && isManufacturer(lastLayer.site)) {
      const bom = getBOM(lastLayer.site, lastLayer.productId);
      if (bom.length > 0) {
        currentProduct = bom[0].component;
      }
    }

    const handleAddSite = () => {
      if (!pathState.selectedSite) return;

      handleAddSiteToPath(
        tree.id,
        path.id,
        parseInt(pathState.selectedSite),
        currentProduct.id,
        pathState.inventoryConfig
      );
      updatePathState({ selectedSite: '' });

      const site = sites.find((s) => s.id === parseInt(pathState.selectedSite));
      if (site && isManufacturer(site)) {
        const bom = getBOM(site, currentProduct.id);
        setTimeout(() => {
          bom.forEach((bomItem) => {
            handleAddComponentConfig(tree.id, path.id, Date.now(), bomItem.componentId, {
              initialInventory: 0,
              targetInventory: bomItem.quantity * 10,
              holdingCost: 0.5,
              backlogCost: 1.0,
            });
          });
        }, 100);
      }
    };

    if (availableSites.length === 0) {
      return (
        <Alert variant="info" className="mt-4">
          No more sites available in the supply chain. Path complete.
        </Alert>
      );
    }

    return (
      <Card variant="outline" className="mt-4 bg-muted/50">
        <CardContent className="pt-4">
          <p className="text-sm font-medium mb-2">Add Site at Layer {currentLayer + 1}</p>
          <p className="text-sm text-muted-foreground mb-4">
            Tracking product: <strong>{currentProduct.name}</strong>
          </p>

          <div className="space-y-4">
            <div>
              <Label htmlFor={`site-select-${pathKey}`}>Select Site</Label>
              <Select
                value={pathState.selectedSite}
                onValueChange={(value) => updatePathState({ selectedSite: value })}
              >
                <SelectTrigger id={`site-select-${pathKey}`}>
                  <SelectValue placeholder="Select a site..." />
                </SelectTrigger>
                <SelectContent>
                  {availableSites.map((site) => {
                    const masterType = (site.master_type || '').toLowerCase();
                    const icon = masterType === 'manufacturer' ? '🏭' : '📦';
                    return (
                      <SelectItem key={site.id} value={String(site.id)}>
                        {icon} {site.name} ({site.dag_type || site.type})
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor={`init-inv-${pathKey}`}>Initial Inventory</Label>
                <Input
                  id={`init-inv-${pathKey}`}
                  type="number"
                  value={pathState.inventoryConfig.initialInventory}
                  onChange={(e) =>
                    updatePathState({
                      inventoryConfig: {
                        ...pathState.inventoryConfig,
                        initialInventory: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  min={0}
                />
              </div>
              <div>
                <Label htmlFor={`target-inv-${pathKey}`}>Target Inventory</Label>
                <Input
                  id={`target-inv-${pathKey}`}
                  type="number"
                  value={pathState.inventoryConfig.targetInventory}
                  onChange={(e) =>
                    updatePathState({
                      inventoryConfig: {
                        ...pathState.inventoryConfig,
                        targetInventory: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  min={0}
                />
              </div>
              <div>
                <Label htmlFor={`holding-cost-${pathKey}`}>Holding Cost</Label>
                <Input
                  id={`holding-cost-${pathKey}`}
                  type="number"
                  value={pathState.inventoryConfig.holdingCost}
                  onChange={(e) =>
                    updatePathState({
                      inventoryConfig: {
                        ...pathState.inventoryConfig,
                        holdingCost: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  min={0}
                  step={0.1}
                />
              </div>
              <div>
                <Label htmlFor={`backlog-cost-${pathKey}`}>Backlog Cost</Label>
                <Input
                  id={`backlog-cost-${pathKey}`}
                  type="number"
                  value={pathState.inventoryConfig.backlogCost}
                  onChange={(e) =>
                    updatePathState({
                      inventoryConfig: {
                        ...pathState.inventoryConfig,
                        backlogCost: parseFloat(e.target.value) || 0,
                      },
                    })
                  }
                  min={0}
                  step={0.1}
                />
              </div>
            </div>

            <Button
              className="w-full"
              onClick={handleAddSite}
              disabled={!pathState.selectedSite}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Add Site to Path
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  };

  const renderLayer = (tree, path, layer, index) => {
    const site = layer.site;
    const product = layer.product;
    const isMfg = isManufacturer(site);
    const bom = isMfg ? getBOM(site, layer.productId) : [];

    return (
      <Card key={layer.id} className="mt-4" style={{ marginLeft: `${index * 2}rem` }}>
        <CardContent className="pt-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              {isMfg ? (
                <Factory className="h-5 w-5 text-primary" />
              ) : (
                <Package className="h-5 w-5 text-primary" />
              )}
              <div>
                <p className="font-medium">
                  {site.name} ({site.dag_type || site.type})
                </p>
                <p className="text-xs text-muted-foreground">
                  Product: {product.name} | Layer {index + 1}
                </p>
              </div>
            </div>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() => handleDeleteLayer(tree.id, path.id, layer.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Delete Layer</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          <div className="grid grid-cols-4 gap-4 mt-4">
            <div>
              <p className="text-xs text-muted-foreground">Initial Inv</p>
              <p className="text-sm">{layer.config.initialInventory}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Target Inv</p>
              <p className="text-sm">{layer.config.targetInventory}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Holding Cost</p>
              <p className="text-sm">${layer.config.holdingCost}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Backlog Cost</p>
              <p className="text-sm">${layer.config.backlogCost}</p>
            </div>
          </div>

          {isMfg && bom.length > 0 && (
            <div className="mt-4">
              <Alert variant="info" className="flex items-start gap-2">
                <LayoutGrid className="h-4 w-4 mt-0.5" />
                <div>
                  <p className="text-xs font-medium">
                    BOM: Producing 1 {product.name} requires:
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {bom.map((bomItem) => (
                      <Badge key={bomItem.componentId} variant="secondary">
                        {bomItem.quantity}x {bomItem.component.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              </Alert>

              {layer.componentConfigs.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-muted-foreground">Component Inventory:</p>
                  {layer.componentConfigs.map((compConfig) => (
                    <div key={compConfig.id} className="mt-1 p-2 bg-muted rounded text-xs">
                      <span className="font-medium">
                        {compConfig.component.name}: Init {compConfig.config.initialInventory}, Target{' '}
                        {compConfig.config.targetInventory}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const renderPath = (tree, path, pathIndex) => {
    const priorityLabel =
      pathIndex === 0 ? 'Primary' : pathIndex === 1 ? 'Secondary' : `Tertiary ${pathIndex - 1}`;

    return (
      <Card key={path.id} variant="outline" className="mt-4">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge variant={pathIndex === 0 ? 'default' : 'secondary'}>{priorityLabel}</Badge>
              <CardTitle className="text-sm">Sourcing Path {pathIndex + 1}</CardTitle>
            </div>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() => handleDeletePath(tree.id, path.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Delete Path</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </CardHeader>
        <CardContent>
          {path.layers.map((layer, index) => renderLayer(tree, path, layer, index))}
          {renderSiteSelector(tree, path)}
        </CardContent>
      </Card>
    );
  };

  const renderTree = (tree) => {
    return (
      <Accordion key={tree.id} type="single" collapsible defaultValue={String(tree.id)}>
        <AccordionItem value={String(tree.id)}>
          <AccordionTrigger>
            <div className="flex items-center gap-3">
              <Network className="h-5 w-5 text-primary" />
              <div className="text-left">
                <p className="font-medium">
                  {tree.marketSite.name} → {tree.product.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  Expected Demand: {tree.expectedDemand} units/period | {tree.paths.length} path(s)
                </p>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="pt-2">
              {tree.paths.map((path, index) => renderPath(tree, path, index))}

              <div className="mt-4">
                <Button
                  variant="outline"
                  onClick={() => handleAddPath(tree.id, tree.paths.length)}
                  disabled={loading}
                  leftIcon={<Plus className="h-4 w-4" />}
                >
                  Add{' '}
                  {tree.paths.length === 0
                    ? 'Primary'
                    : tree.paths.length === 1
                    ? 'Secondary'
                    : 'Another'}{' '}
                  Sourcing Path
                </Button>
              </div>

              <div className="mt-4 flex justify-end">
                <Button
                  variant="outline"
                  className="text-destructive"
                  onClick={() => handleDeleteTree(tree.id)}
                  leftIcon={<Trash2 className="h-4 w-4" />}
                >
                  Delete Configuration
                </Button>
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    );
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-lg font-semibold">Product Sourcing Configuration</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Define sourcing paths from market demand through the supply chain DAG
          </p>
        </div>
        <div className="flex gap-2">
          {sourcingTrees.length > 0 && (
            <Button
              onClick={handleSaveAll}
              disabled={loading}
              leftIcon={<Save className="h-4 w-4" />}
            >
              Save All Configurations
            </Button>
          )}
          {navigationButtons}
        </div>
      </div>

      {marketDemandSites.length === 0 && (
        <Alert variant="warning" className="mb-4">
          No market demand sites defined. Add a site with master type "Market Demand" in the Sites step.
        </Alert>
      )}

      {productList.length === 0 && (
        <Alert variant="warning" className="mb-4">
          No products defined. Add products in the Products step.
        </Alert>
      )}

      {marketDemandSites.length > 0 && productList.length > 0 && (
        <div>
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Network className="h-5 w-5 text-primary" />
                <CardTitle>Start New Sourcing Configuration</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-12 gap-4">
                <div className="col-span-4">
                  <Label htmlFor="market-demand-site">Market Demand Site</Label>
                  <Select
                    value={selectedMarket}
                    onValueChange={setSelectedMarket}
                    disabled={loading}
                  >
                    <SelectTrigger id="market-demand-site">
                      <SelectValue placeholder="Select market demand site..." />
                    </SelectTrigger>
                    <SelectContent>
                      {marketDemandSites.map((site) => (
                        <SelectItem key={site.id} value={String(site.id)}>
                          <div className="flex items-center gap-2">
                            <TrendingUp className="h-4 w-4" />
                            {site.name}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1">Select the demand source</p>
                </div>

                <div className="col-span-4">
                  <Label htmlFor="finished-good">Finished Good Product</Label>
                  <Select
                    value={selectedProduct}
                    onValueChange={setSelectedProduct}
                    disabled={loading || !selectedMarket}
                  >
                    <SelectTrigger id="finished-good">
                      <SelectValue placeholder="Select product..." />
                    </SelectTrigger>
                    <SelectContent>
                      {productList.map((product) => (
                        <SelectItem key={product.id} value={String(product.id)}>
                          {product.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1">Select the product demanded</p>
                </div>

                <div className="col-span-2">
                  <Label htmlFor="expected-demand">Expected Demand</Label>
                  <Input
                    id="expected-demand"
                    type="number"
                    value={expectedDemand}
                    onChange={(e) => setExpectedDemand(parseFloat(e.target.value) || 0)}
                    disabled={loading}
                    min={0}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Units per period</p>
                </div>

                <div className="col-span-2 flex items-end">
                  <Button
                    className="w-full"
                    onClick={handleStartConfiguration}
                    disabled={loading || !selectedMarket || !selectedProduct}
                    leftIcon={<Plus className="h-4 w-4" />}
                  >
                    Start
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {sourcingTrees.length > 0 && (
            <div className="mb-6">
              <p className="font-medium mb-2">Active Sourcing Configurations</p>
              {sourcingTrees.map((tree) => renderTree(tree))}
            </div>
          )}

          {productSiteConfigs.length > 0 && (
            <div className="mt-8">
              <hr className="mb-4" />
              <p className="font-medium mb-2">Saved Configurations ({productSiteConfigs.length})</p>
              <Alert variant="info">
                {productSiteConfigs.length} product-site configuration(s) exist in the database. Use the form
                above to create new sourcing trees.
              </Alert>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SourcingTreeForm;
