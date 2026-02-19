import { useMemo, useState } from 'react';
import {
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
import { RotateCcw, Pencil, Trash2, Plus } from 'lucide-react';

import {
  DEFAULT_SITE_TYPE_DEFINITIONS,
  sortSiteTypeDefinitions,
  canonicalizeSiteTypeKey,
} from '../../services/supplyChainConfigService';

const MASTER_TYPE_OPTIONS = [
  {
    value: 'market_demand',
    label: 'Market Demand',
    description: 'Terminal demand sites (customers, retailers, end consumers)',
    examples: 'Retail Stores, Online Customers, Wholesale Buyers',
    color: 'bg-blue-100 text-blue-800 border-blue-200',
  },
  {
    value: 'inventory',
    label: 'Inventory',
    description: 'Storage and fulfillment sites (DCs, warehouses, hubs)',
    examples: 'Distribution Centers, Regional DCs, Fulfillment Centers',
    color: 'bg-green-100 text-green-800 border-green-200',
  },
  {
    value: 'manufacturer',
    label: 'Manufacturer',
    description: 'Production sites with Bill of Materials (factories, plants)',
    examples: 'Manufacturing Plants, Assembly Lines, Bottling Facilities',
    color: 'bg-purple-100 text-purple-800 border-purple-200',
  },
  {
    value: 'market_supply',
    label: 'Market Supply',
    description: 'Upstream source sites (suppliers, vendors, raw materials)',
    examples: 'Raw Material Suppliers, Component Vendors, Ingredient Providers',
    color: 'bg-orange-100 text-orange-800 border-orange-200',
  },
];

const SiteTypeManager = ({ definitions = [], onChange, loading = false, onDeleteType, navigationButtons = null }) => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState('edit');
  const [draft, setDraft] = useState({
    type: '',
    label: '',
    master_type: '',
    order: 0,
    is_required: false,
    originalType: null,
  });

  const sortedDefinitions = useMemo(
    () => sortSiteTypeDefinitions(definitions),
    [definitions]
  );

  // Group definitions by master type for organized display
  const groupedDefinitions = useMemo(() => {
    const groups = {};
    MASTER_TYPE_OPTIONS.forEach((opt) => {
      groups[opt.value] = {
        ...opt,
        definitions: [],
      };
    });
    sortedDefinitions.forEach((def) => {
      const masterType = def.master_type || 'inventory';
      if (groups[masterType]) {
        groups[masterType].definitions.push(def);
      } else {
        groups['inventory'].definitions.push(def);
      }
    });
    return groups;
  }, [sortedDefinitions]);

  const handleReset = () => {
    onChange(DEFAULT_SITE_TYPE_DEFINITIONS.map((definition) => ({ ...definition })));
  };

  const openDialog = (definition = null) => {
    if (definition) {
      setDialogMode('edit');
      setDraft({ ...definition, originalType: definition.type });
    } else {
      setDialogMode('add');
      setDraft({
        type: '',
        label: '',
        master_type: 'inventory',
        order: definitions.length,
        is_required: false,
        originalType: null,
      });
    }
    setDialogOpen(true);
  };

  const closeDialog = () => setDialogOpen(false);

  const handleDialogChange = (field, value) => {
    const parsedValue = field === 'order' ? parseInt(value, 10) || 0 : value;
    setDraft((prev) => ({ ...prev, [field]: parsedValue }));
  };

  const handleDialogSave = () => {
    const typeKey = canonicalizeSiteTypeKey(draft.type);
    if (!typeKey) return;

    const payload = {
      ...draft,
      type: typeKey,
    };
    delete payload.originalType;

    const normalizedDefinitions = definitions.map((definition) => ({
      ...definition,
      type: canonicalizeSiteTypeKey(definition.type),
    }));

    let next;
    if (dialogMode === 'edit') {
      const original = canonicalizeSiteTypeKey(draft.originalType) || typeKey;
      next = normalizedDefinitions.map((def) => (def.type === original ? { ...payload } : def));
    } else {
      next = [
        ...normalizedDefinitions.filter((def) => def.type !== typeKey),
        { ...payload },
      ];
    }
    onChange(next);
    setDialogOpen(false);
  };

  const handleDelete = (typeKey) => {
    const normalizedType = canonicalizeSiteTypeKey(typeKey);
    const existingDefinition = definitions.find(
      (definition) => canonicalizeSiteTypeKey(definition?.type) === normalizedType
    );

    if (onDeleteType) {
      onDeleteType(existingDefinition || { type: normalizedType });
      return;
    }

    const next = definitions.filter(
      (definition) => canonicalizeSiteTypeKey(definition?.type) !== normalizedType
    );
    onChange(next);
  };

  return (
    <Card variant="outline">
      <CardHeader>
        <div className="flex items-center justify-between w-full">
          <div>
            <CardTitle>Supply Chain Site Types</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Define site types organized by their role in the supply chain
            </p>
          </div>
          <div className="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleReset}
                    disabled={loading}
                    leftIcon={<RotateCcw className="h-4 w-4" />}
                  >
                    Reset
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Reset to default site types</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {navigationButtons}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Master Type Legend */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6 p-4 bg-muted/30 rounded-lg">
          {MASTER_TYPE_OPTIONS.map((opt) => (
            <div key={opt.value} className={`p-3 rounded-md border ${opt.color}`}>
              <div className="font-semibold text-sm">{opt.label}</div>
              <div className="text-xs mt-1 opacity-80">{opt.description}</div>
              <div className="text-xs mt-1 italic opacity-60">e.g., {opt.examples}</div>
            </div>
          ))}
        </div>

        {/* Grouped Site Types */}
        <div className="space-y-6">
          {MASTER_TYPE_OPTIONS.map((masterType) => {
            const group = groupedDefinitions[masterType.value];
            return (
              <div key={masterType.value} className="border rounded-lg overflow-hidden">
                <div className={`px-4 py-2 border-b ${masterType.color}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold">{masterType.label}</span>
                      <span className="text-xs ml-2 opacity-70">
                        ({group.definitions.length} type{group.definitions.length !== 1 ? 's' : ''})
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setDialogMode('add');
                        setDraft({
                          type: '',
                          label: '',
                          master_type: masterType.value,
                          order: definitions.length,
                          is_required: false,
                          originalType: null,
                        });
                        setDialogOpen(true);
                      }}
                      disabled={loading}
                      className="h-7"
                    >
                      <Plus className="h-3 w-3 mr-1" />
                      Add
                    </Button>
                  </div>
                </div>
                {group.definitions.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[40%]">Site Type</TableHead>
                        <TableHead className="w-[20%]">DAG Order</TableHead>
                        <TableHead className="w-[25%]">Attributes</TableHead>
                        <TableHead className="w-[15%] text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {group.definitions.map((definition) => {
                        const typeKey = definition.type || '';
                        return (
                          <TableRow key={typeKey}>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <span className="font-medium capitalize">
                                  {definition.label || typeKey.replace(/_/g, ' ')}
                                </span>
                                {definition.is_required && (
                                  <Badge variant="info">Required</Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>
                              <span className="text-sm">
                                {Number.isFinite(definition.order) ? definition.order : '—'}
                              </span>
                            </TableCell>
                            <TableCell>
                              <span className="text-xs text-muted-foreground">
                                Position {Number.isFinite(definition.order) ? definition.order : '—'} in flow
                              </span>
                            </TableCell>
                            <TableCell className="text-right">
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => openDialog(definition)}
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
                                      onClick={() => handleDelete(typeKey)}
                                      disabled={loading || definition.is_required}
                                      className={definition.is_required ? '' : 'text-destructive'}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Delete</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                    No site types defined for {masterType.label}. Click "Add" to create one.
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex justify-end mt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => openDialog(null)}
            disabled={loading}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Site Type
          </Button>
        </div>
      </CardContent>

      <Modal
        isOpen={dialogOpen}
        onClose={closeDialog}
        title={dialogMode === 'edit' ? 'Edit DAG Site Type' : 'Add DAG Site Type'}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeDialog} disabled={loading}>
              Cancel
            </Button>
            <Button
              onClick={handleDialogSave}
              disabled={loading || !draft.type || !draft.master_type}
            >
              {dialogMode === 'edit' ? 'Save' : 'Add'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="dag-type">DAG Type</Label>
            <Input
              id="dag-type"
              value={draft.type}
              onChange={(e) => handleDialogChange('type', e.target.value)}
              disabled={loading}
            />
            <p className="text-xs text-muted-foreground mt-1">
              Unique key used for this DAG layer
            </p>
          </div>
          <div>
            <Label htmlFor="display-label">Display Label</Label>
            <Input
              id="display-label"
              value={draft.label}
              onChange={(e) => handleDialogChange('label', e.target.value)}
              disabled={loading}
            />
          </div>
          <div>
            <Label htmlFor="master-type">Master Type</Label>
            <Select
              value={draft.master_type}
              onValueChange={(value) => handleDialogChange('master_type', value)}
              disabled={loading}
            >
              <SelectTrigger id="master-type">
                <SelectValue placeholder="Select master type" />
              </SelectTrigger>
              <SelectContent>
                {MASTER_TYPE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    <div className="flex flex-col">
                      <span className="font-medium">{opt.label}</span>
                      <span className="text-xs text-muted-foreground">{opt.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {draft.master_type && (
              <p className="text-xs text-muted-foreground mt-1">
                {MASTER_TYPE_OPTIONS.find((opt) => opt.value === draft.master_type)?.examples &&
                  `Examples: ${MASTER_TYPE_OPTIONS.find((opt) => opt.value === draft.master_type)?.examples}`}
              </p>
            )}
          </div>
          <div>
            <Label htmlFor="dag-order">DAG Order</Label>
            <Input
              id="dag-order"
              type="number"
              value={draft.order}
              onChange={(e) => handleDialogChange('order', e.target.value)}
              disabled={loading}
            />
            <p className="text-xs text-muted-foreground mt-1">
              Lower numbers appear closer to demand
            </p>
          </div>
        </div>
      </Modal>
    </Card>
  );
};

export default SiteTypeManager;
