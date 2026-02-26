import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Modal,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Switch,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import { Save, ArrowLeft, Check } from 'lucide-react';
import { useFormik } from '../../hooks/useFormik';
import { useSnackbar } from 'notistack';
import { api } from '../../services/api';
import { getAdminDashboardPath } from '../../utils/adminDashboardState';

// Import services - AWS SC DM compliant naming (products not items, sites not nodes)
import {
  getSupplyChainConfigById,
  createSupplyChainConfig,
  updateSupplyChainConfig,
  getProducts,
  getSites,
  getLanes,
  getProductSiteConfigs,
  getMarkets,
  getMarketDemands,
  createProduct,
  updateProduct,
  deleteProduct,
  createSite,
  updateSite,
  deleteSite,
  createLane,
  updateLane,
  deleteLane,
  createProductSiteConfig,
  updateProductSiteConfig,
  createMarket,
  updateMarket,
  deleteMarket,
  createMarketDemand,
  updateMarketDemand,
  deleteMarketDemand,
  getSiteTypeDisplayName,
  DEFAULT_CONFIG,
  CLASSIC_SUPPLY_CHAIN,
  DEFAULT_SITE_TYPE_DEFINITIONS,
  sortSiteTypeDefinitions,
  canonicalizeSiteTypeKey,
} from '../../services/supplyChainConfigService';

// Import sub-components
import SiteForm from './SiteForm';
import TransportationLaneForm from './TransportationLaneForm';  // AWS SC DM standard
import ProductForm from './ProductForm';
import SourcingTreeForm from './SourcingTreeForm';
import BOMForm from './BOMForm';
import MarketManager from './MarketManager';
import MarketDemandForm from './MarketDemandForm';
import SiteTypeManager from './SiteTypeManager';

const canonicalizeMasterType = (rawMaster, typeKey) => {
  const canonicalMaster = canonicalizeSiteTypeKey(rawMaster);
  const canonicalType = canonicalizeSiteTypeKey(typeKey);

  if (['market_demand', 'market', 'demand'].includes(canonicalMaster)) return 'market_demand';
  if (['market_supply', 'supply'].includes(canonicalMaster)) return 'market_supply';
  if (['manufacturer', 'mfg'].includes(canonicalMaster)) return 'manufacturer';
  if (['inventory', 'retailer', 'wholesaler', 'distributor', 'supplier'].includes(canonicalMaster)) {
    return 'inventory';
  }

  if (['market_demand', 'market', 'demand'].includes(canonicalType)) return 'market_demand';
  if (['market_supply', 'supply'].includes(canonicalType)) return 'market_supply';
  if (/mfg|manufactur/.test(canonicalType)) return 'manufacturer';
  if (
    ['retailer', 'wholesaler', 'distributor', 'inventory', 'supplier'].includes(canonicalType) ||
    !canonicalType
  ) {
    return 'inventory';
  }

  return 'inventory';
};

const getSiteDagType = (site) =>
  site?.dag_type ||
  site?.dagType ||
  site?.type ||
  site?.master_type ||
  site?.masterType ||
  '';

const extractMasterTypesFromSites = (sites = []) =>
  sites.reduce((acc, site = {}) => {
    const dagKey = canonicalizeSiteTypeKey(site?.dag_type || site?.type);
    const masterKey = canonicalizeSiteTypeKey(site?.master_type || site?.type);
    if (dagKey) {
      acc[dagKey] = masterKey;
    }
    return acc;
  }, {});

const normalizeNodeTypeDefinitions = (definitions = [], masterTypeHints = {}) => {
  if (!Array.isArray(definitions)) {
    return [];
  }

  const hintMap = Object.entries(masterTypeHints || {}).reduce((acc, [key, value]) => {
    const typeKey = canonicalizeSiteTypeKey(key);
    const masterKey = canonicalizeSiteTypeKey(value);
    if (typeKey) {
      acc[typeKey] = masterKey;
    }
    return acc;
  }, {});

  const deduped = new Map();
  definitions.forEach((definition = {}, index) => {
    const typeKey = canonicalizeSiteTypeKey(definition?.type || definition?.label || '');
    if (!typeKey) {
      return;
    }
    const normalizedMaster = canonicalizeMasterType(
      definition?.master_type ?? hintMap[typeKey],
      typeKey
    );

    deduped.set(typeKey, {
      ...definition,
      type: typeKey,
      order: Number.isFinite(definition?.order) ? definition.order : index,
      is_required: Boolean(definition?.is_required),
      master_type: normalizedMaster,
    });
  });
  return sortSiteTypeDefinitions(Array.from(deduped.values()));
};

const STEPS = [
  'Basic Information',
  'Products',
  'Sites',
  'Lanes',
  'Product Sourcing',
  'Bill of Materials',
  'Markets',
  'Market Demands',
  'Review & Save'
];

const SupplyChainConfigForm = ({
  basePath = '/supply-chain-config',
  allowGroupSelection = true,
  defaultGroupId = null,
} = {}) => {
  const { id } = useParams();
  const isEditMode = Boolean(id);
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();

  const initialBasicFormValues = {
    name: '',
    description: '',
    is_active: false,
    tenant_id: defaultGroupId ? String(defaultGroupId) : '',
    time_bucket: 'week',
  };

  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(isEditMode);
  const [error, setError] = useState(null);
  const [confirmDeleteType, setConfirmDeleteType] = useState({
    open: false,
    definition: null,
    sites: [],
  });

  const [basicStepConfirmOpen, setBasicStepConfirmOpen] = useState(false);
  const [pendingStepIndex, setPendingStepIndex] = useState(null);

  // Data state
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG, tenant_id: null });
  const [products, setProducts] = useState(isEditMode ? [] : CLASSIC_SUPPLY_CHAIN.products);
  const [sites, setSites] = useState(isEditMode ? [] : CLASSIC_SUPPLY_CHAIN.sites);
  const [lanes, setLanes] = useState(isEditMode ? [] : CLASSIC_SUPPLY_CHAIN.lanes);
  const [productSiteConfigs, setProductSiteConfigs] = useState([]);
  const [markets, setMarkets] = useState([]);
  const [marketDemands, setMarketDemands] = useState([]);
  const [nodeTypeDefinitions, setNodeTypeDefinitions] = useState(() =>
    normalizeNodeTypeDefinitions(
      DEFAULT_SITE_TYPE_DEFINITIONS.map((definition) => ({ ...definition }))
    )
  );
  const [savedBasicInfo, setSavedBasicInfo] = useState(() => ({ ...initialBasicFormValues }));
  const [savedNodeTypeDefinitions, setSavedNodeTypeDefinitions] = useState(() =>
    normalizeNodeTypeDefinitions(
      DEFAULT_SITE_TYPE_DEFINITIONS.map((definition) => ({ ...definition }))
    )
  );
  const handleNodeTypeDefinitionsChange = (definitions) => {
    setNodeTypeDefinitions(
      normalizeNodeTypeDefinitions(definitions, extractMasterTypesFromSites(sites))
    );
  };

  const removeNodeTypeDefinition = (typeKey) => {
    const normalizedType = canonicalizeSiteTypeKey(typeKey);
    if (!normalizedType) return;
    setNodeTypeDefinitions((prev) =>
      prev.filter((definition) => canonicalizeSiteTypeKey(definition?.type) !== normalizedType)
    );
  };

  const removeSitesForTypeFromState = (typeKey, sitesToDelete = []) => {
    setSites((prev) =>
      prev.filter((site) => canonicalizeSiteTypeKey(site?.type) !== typeKey)
    );
    if (sitesToDelete.length > 0) {
      const idsToRemove = new Set(sitesToDelete.map((site) => Number(site.id)));
      setLanes((prev) =>
        prev.filter(
          (lane) =>
            !idsToRemove.has(Number(lane.from_site_id)) &&
            !idsToRemove.has(Number(lane.to_site_id))
        )
      );
      setProductSiteConfigs((prev) =>
        prev.filter((config) => !idsToRemove.has(Number(config.site_id)))
      );
    }
  };

  const handleConfirmDeleteType = (definition) => {
    const normalizedType = canonicalizeSiteTypeKey(definition?.type);
    if (!normalizedType) return;
    const sitesForType = sites.filter(
      (site) => canonicalizeSiteTypeKey(site?.type) === normalizedType
    );

    if (sitesForType.length === 0) {
      removeNodeTypeDefinition(normalizedType);
      return;
    }

    setConfirmDeleteType({
      open: true,
      definition,
      sites: sitesForType,
    });
  };

  const handleDeleteTypeCancel = () => {
    setConfirmDeleteType({ open: false, definition: null, sites: [] });
  };

  const handleDeleteTypeConfirm = async () => {
    if (!confirmDeleteType.definition) return;
    const normalizedType = canonicalizeSiteTypeKey(confirmDeleteType.definition.type);
    if (!normalizedType) {
      handleDeleteTypeCancel();
      return;
    }

    if (!isEditMode) {
      removeSitesForTypeFromState(normalizedType, confirmDeleteType.sites);
      removeNodeTypeDefinition(normalizedType);
      enqueueSnackbar('DAG/Group type and associated sites deleted', { variant: 'success' });
      handleDeleteTypeCancel();
      return;
    }

    try {
      setLoading(true);
      const sitesToDelete = [...confirmDeleteType.sites];

      // Delete all sites belonging to the DAG/Group type
      for (const site of sitesToDelete) {
        try {
          await deleteSite(id, site.id);
        } catch (err) {
          console.error('Error deleting site while removing DAG type:', err);
          enqueueSnackbar('Failed to delete site linked to DAG type', { variant: 'error' });
          setLoading(false);
          return;
        }
      }

      await Promise.all([fetchSites(), fetchLanes(), fetchProductSiteConfigs()]);
      removeNodeTypeDefinition(normalizedType);
      enqueueSnackbar('DAG/Group type and associated sites deleted', { variant: 'success' });
    } finally {
      setLoading(false);
      handleDeleteTypeCancel();
    }
  };
  // Organization selection state
  const [organizations, setOrganizations] = useState([]);
  const [organizationsLoading, setOrganizationsLoading] = useState(false);
  const [organizationsError, setOrganizationsError] = useState(null);

  // Formik form
  const validateForm = useCallback((values) => {
    const errors = {};
    if (!values.name || !values.name.trim()) {
      errors.name = 'Name is required';
    }

    if (allowGroupSelection) {
      const groupValue = values.tenant_id ?? '';
      if (!String(groupValue).trim()) {
        errors.tenant_id = 'Organization is required';
      }
    }

    if (!values.time_bucket) {
      errors.time_bucket = 'Time bucket is required';
    }

    return errors;
  }, [allowGroupSelection]);

  const formik = useFormik({
    initialValues: {
      ...initialBasicFormValues,
    },
    validate: validateForm,
    onSubmit: async (values) => {
      try {
        setLoading(true);

        const effectiveGroupId =
          values.tenant_id || (defaultGroupId ? String(defaultGroupId) : '');

        const payload = {
          name: values.name,
          description: values.description,
          is_active: values.is_active,
          time_bucket: values.time_bucket,
          site_type_definitions: nodeTypeDefinitions.map((definition, index) => ({
            ...definition,
            order: Number.isFinite(definition?.order) ? definition.order : index,
          })),
        };

        // Only include tenant_id in the payload if:
        // 1. Creating a new config (not edit mode), OR
        // 2. Editing and allowGroupSelection is true (system admin)
        if (effectiveGroupId && (!isEditMode || allowGroupSelection)) {
          payload.tenant_id = Number(effectiveGroupId);
        }

        if (isEditMode) {
          await updateSupplyChainConfig(id, payload);
          enqueueSnackbar('Configuration updated successfully', { variant: 'success' });
          await fetchConfig();
        } else {
          const newConfig = await createSupplyChainConfig(payload);
          enqueueSnackbar('Configuration created successfully', { variant: 'success' });
          navigate(`${basePath}/edit/${newConfig.id}`);
        }
      } catch (err) {
        console.error('Error saving configuration:', err);
        enqueueSnackbar('Failed to save configuration', { variant: 'error' });
      } finally {
        setLoading(false);
      }
    },
  });

  const { setFieldValue, setValues } = formik;

  const basicInfoFingerprint = useMemo(() => {
    const groupIdValue = formik.values.tenant_id ? String(formik.values.tenant_id) : '';
    return JSON.stringify({
      name: formik.values.name || '',
      description: formik.values.description || '',
      is_active: Boolean(formik.values.is_active),
      tenant_id: groupIdValue,
      time_bucket: (formik.values.time_bucket || 'week').toLowerCase(),
    });
  }, [
    formik.values.name,
    formik.values.description,
    formik.values.is_active,
    formik.values.tenant_id,
    formik.values.time_bucket,
  ]);

  const savedBasicFingerprint = useMemo(() => JSON.stringify(savedBasicInfo), [savedBasicInfo]);
  const nodeTypeFingerprint = useMemo(
    () => JSON.stringify(nodeTypeDefinitions),
    [nodeTypeDefinitions]
  );
  const savedNodeTypeFingerprint = useMemo(
    () => JSON.stringify(savedNodeTypeDefinitions),
    [savedNodeTypeDefinitions]
  );

  const isBasicStepDirty = useMemo(
    () =>
      isEditMode &&
      (basicInfoFingerprint !== savedBasicFingerprint ||
        nodeTypeFingerprint !== savedNodeTypeFingerprint),
    [
      isEditMode,
      basicInfoFingerprint,
      savedBasicFingerprint,
      nodeTypeFingerprint,
      savedNodeTypeFingerprint,
    ]
  );

  useEffect(() => {
    if (!allowGroupSelection) {
      setFieldValue('tenant_id', defaultGroupId ? String(defaultGroupId) : '', false);
      return;
    }

    let isMounted = true;

    const loadOrganizations = async () => {
      try {
        setOrganizationsLoading(true);
        const response = await api.get('/tenants');
        if (!isMounted) return;
        setOrganizations(response.data || []);
        setOrganizationsError(null);
      } catch (err) {
        console.error('Error loading organizations:', err);
        if (!isMounted) return;
        setOrganizations([]);
        setOrganizationsError('Unable to load organizations');
      } finally {
        if (isMounted) {
          setOrganizationsLoading(false);
        }
      }
    };

    loadOrganizations();

    return () => {
      isMounted = false;
    };
  }, [allowGroupSelection, defaultGroupId, setFieldValue]);

  useEffect(() => {
    if (!isEditMode && allowGroupSelection) {
      setFieldValue('tenant_id', defaultGroupId ? String(defaultGroupId) : '', false);
    }
  }, [allowGroupSelection, defaultGroupId, isEditMode, setFieldValue]);

  const fetchProducts = useCallback(async () => {
    const productsData = await getProducts(id);
    setProducts(productsData);
    return productsData;
  }, [id]);

  const fetchSites = useCallback(async () => {
    const sitesData = await getSites(id);
    setSites(sitesData);
    return sitesData;
  }, [id]);

  const fetchLanes = useCallback(async () => {
    const lanesData = await getLanes(id);
    setLanes(lanesData);
    return lanesData;
  }, [id]);

  const fetchProductSiteConfigs = useCallback(async () => {
    const configsData = await getProductSiteConfigs(id);
    setProductSiteConfigs(configsData);
    return configsData;
  }, [id]);

  const fetchMarkets = useCallback(async () => {
    const marketsData = await getMarkets(id);
    setMarkets(marketsData);
    return marketsData;
  }, [id]);

  const fetchMarketDemands = useCallback(async () => {
    const demandsData = await getMarketDemands(id);
    setMarketDemands(demandsData);
    return demandsData;
  }, [id]);

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      const configData = await getSupplyChainConfigById(id);
      setConfig(configData);
      const normalizedDefinitions = normalizeNodeTypeDefinitions(
        (configData?.site_type_definitions || DEFAULT_SITE_TYPE_DEFINITIONS).map((definition) => ({
          ...definition,
        })),
        extractMasterTypesFromSites(configData?.sites)
      );
      setNodeTypeDefinitions(normalizedDefinitions);
      setSavedNodeTypeDefinitions(normalizedDefinitions);

      // Set form values
      const savedValues = {
        name: configData.name,
        description: configData.description || '',
        is_active: configData.is_active || false,
        tenant_id: configData.tenant_id ? String(configData.tenant_id) : '',
        time_bucket: (configData.time_bucket || 'week').toLowerCase(),
      };
      setValues(savedValues);
      setSavedBasicInfo(savedValues);

      // Fetch related data
      await Promise.all([
        fetchProducts(),
        fetchSites(),
        fetchLanes(),
        fetchProductSiteConfigs(),
        fetchMarkets(),
        fetchMarketDemands(),
      ]);

      setError(null);
    } catch (err) {
      console.error('Error fetching configuration:', err);
      setError('Failed to load configuration data');
      enqueueSnackbar('Failed to load configuration', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  }, [
    enqueueSnackbar,
    fetchProductSiteConfigs,
    fetchMarkets,
    fetchProducts,
    fetchLanes,
    fetchMarketDemands,
    fetchSites,
    id,
    setValues,
  ]);

  useEffect(() => {
    if (isEditMode) {
      fetchConfig();
    }
  }, [isEditMode, fetchConfig]);

  const applySavedBasicInformation = () => {
    setValues({
      name: savedBasicInfo.name,
      description: savedBasicInfo.description,
      is_active: savedBasicInfo.is_active,
      tenant_id: savedBasicInfo.tenant_id,
      time_bucket: savedBasicInfo.time_bucket,
    });
    setNodeTypeDefinitions(
      savedNodeTypeDefinitions.map((definition) => ({ ...definition }))
    );
  };

  const handleSaveBasicInfo = async () => {
    if (!isEditMode || !id) {
      return false;
    }

    try {
      setLoading(true);
      const normalizedDefinitions = normalizeNodeTypeDefinitions(
        nodeTypeDefinitions,
        extractMasterTypesFromSites(sites)
      );
      const payload = {
        name: formik.values.name,
        description: formik.values.description || '',
        is_active: Boolean(formik.values.is_active),
        time_bucket: (formik.values.time_bucket || 'week').toLowerCase(),
        site_type_definitions: normalizedDefinitions,
      };

      if (allowGroupSelection) {
        const groupValue = formik.values.tenant_id ? String(formik.values.tenant_id).trim() : '';
        if (groupValue) {
          const parsed = Number(groupValue);
          payload.tenant_id = Number.isNaN(parsed) ? null : parsed;
        } else {
          payload.tenant_id = null;
        }
      }

      const updatedConfig = await updateSupplyChainConfig(id, payload);
      const updatedDefinitions = normalizeNodeTypeDefinitions(
        updatedConfig.site_type_definitions || normalizedDefinitions,
        extractMasterTypesFromSites(updatedConfig?.sites || sites)
      );
      const savedValues = {
        name: updatedConfig.name || '',
        description: updatedConfig.description || '',
        is_active: Boolean(updatedConfig.is_active),
        tenant_id: updatedConfig.tenant_id ? String(updatedConfig.tenant_id) : '',
        time_bucket: (updatedConfig.time_bucket || 'week').toLowerCase(),
      };

      setConfig(updatedConfig);
      setNodeTypeDefinitions(updatedDefinitions);
      setSavedNodeTypeDefinitions(updatedDefinitions);
      setValues(savedValues);
      setSavedBasicInfo(savedValues);
      enqueueSnackbar('Basic information saved', { variant: 'success' });
      return true;
    } catch (err) {
      console.error('Error saving basic information:', err);
      enqueueSnackbar(
        err.response?.data?.detail || 'Failed to save basic information',
        { variant: 'error' }
      );
      return false;
    } finally {
      setLoading(false);
    }
  };

  const attemptStepChange = (targetStep) => {
    if (targetStep <= activeStep) {
      setActiveStep(targetStep);
      return;
    }
    if (activeStep === 0 && targetStep > activeStep && isBasicStepDirty) {
      setPendingStepIndex(targetStep);
      setBasicStepConfirmOpen(true);
      return;
    }
    setActiveStep(targetStep);
  };

  const handleConfirmSave = async () => {
    setBasicStepConfirmOpen(false);
    const saved = await handleSaveBasicInfo();
    if (saved && pendingStepIndex !== null) {
      setActiveStep(pendingStepIndex);
      setPendingStepIndex(null);
    } else if (!saved) {
      setBasicStepConfirmOpen(true);
    }
  };

  const handleConfirmDiscard = () => {
    applySavedBasicInformation();
    setBasicStepConfirmOpen(false);
    if (pendingStepIndex !== null) {
      setActiveStep(pendingStepIndex);
    }
    setPendingStepIndex(null);
  };

  const handleConfirmCancel = () => {
    setBasicStepConfirmOpen(false);
    setPendingStepIndex(null);
  };

  const handleBack = () => {
    if (activeStep === 0) {
      navigate(-1);
    } else {
      setActiveStep((prevStep) => prevStep - 1);
    }
  };

  const handleNext = async () => {
    if (activeStep === STEPS.length - 1) {
      await formik.submitForm();
    } else {
      attemptStepChange(activeStep + 1);
    }
  };

  const handleStep = (step) => {
    if (step < activeStep) {
      setActiveStep(step);
    }
  };

  // Create navigation buttons for form headers
  const getNavigationButtons = () => {
    return (
      <>
        {activeStep > 0 && (
          <Button
            variant="outline"
            onClick={handleBack}
            disabled={loading}
          >
            Back
          </Button>
        )}
        {activeStep < STEPS.length - 1 && (
          <Button
            onClick={handleNext}
            disabled={loading}
          >
            Next
          </Button>
        )}
      </>
    );
  };

  // Render step content
  const renderStepContent = (step) => {
    switch (step) {
      case 0: // Basic Information
        return (
          <div className="flex flex-col gap-6">
            <div className="grid grid-cols-12 gap-6">
              <div className="col-span-12">
                <Label htmlFor="name">Configuration Name</Label>
                <Input
                  id="name"
                  name="name"
                  value={formik.values.name}
                  onChange={formik.handleChange}
                  onBlur={formik.handleBlur}
                  disabled={loading}
                  className={formik.touched.name && formik.errors.name ? 'border-destructive' : ''}
                />
                {formik.touched.name && formik.errors.name && (
                  <span className="text-sm text-destructive mt-1">{formik.errors.name}</span>
                )}
              </div>
              <div className="col-span-12">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  name="description"
                  rows={4}
                  value={formik.values.description}
                  onChange={formik.handleChange}
                  onBlur={formik.handleBlur}
                  disabled={loading}
                />
                {formik.touched.description && formik.errors.description && (
                  <span className="text-sm text-destructive mt-1">{formik.errors.description}</span>
                )}
              </div>
              <div className="col-span-12 sm:col-span-6">
                <Label htmlFor="time_bucket">Time Bucket</Label>
                <Select
                  value={formik.values.time_bucket}
                  onValueChange={(value) => formik.setFieldValue('time_bucket', value)}
                  disabled={loading}
                >
                  <SelectTrigger id="time_bucket" className={formik.touched.time_bucket && formik.errors.time_bucket ? 'border-destructive' : ''}>
                    <SelectValue placeholder="Select time bucket" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="day">Day</SelectItem>
                    <SelectItem value="week">Week</SelectItem>
                    <SelectItem value="month">Month</SelectItem>
                  </SelectContent>
                </Select>
                <span className={`text-sm mt-1 ${formik.touched.time_bucket && formik.errors.time_bucket ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {formik.touched.time_bucket && formik.errors.time_bucket
                    ? formik.errors.time_bucket
                    : 'Controls whether lead times are interpreted in days, weeks, or months.'}
                </span>
              </div>
              {allowGroupSelection && (
                <div className="col-span-12">
                  <Label htmlFor="tenant_id">Organization</Label>
                  <Select
                    value={formik.values.tenant_id}
                    onValueChange={(value) => formik.setFieldValue('tenant_id', value)}
                    disabled={loading || organizationsLoading}
                  >
                    <SelectTrigger id="tenant_id" className={formik.touched.tenant_id && formik.errors.tenant_id ? 'border-destructive' : ''}>
                      <SelectValue placeholder="Select an organization" />
                    </SelectTrigger>
                    <SelectContent>
                      {organizations.length === 0 && !organizationsLoading ? (
                        <SelectItem value="" disabled>
                          No organizations available
                        </SelectItem>
                      ) : (
                        organizations.map((org) => (
                          <SelectItem key={org.id} value={String(org.id)}>
                            {org.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  {formik.touched.tenant_id && formik.errors.tenant_id ? (
                    <span className="text-sm text-destructive mt-1">{formik.errors.tenant_id}</span>
                  ) : organizationsError ? (
                    <span className="text-sm text-destructive mt-1">{organizationsError}</span>
                  ) : null}
                </div>
              )}
              {isEditMode && (
                <div className="col-span-12">
                  <div className="flex items-center gap-2">
                    <Switch
                      id="is_active"
                      checked={formik.values.is_active}
                      onCheckedChange={(checked) => formik.setFieldValue('is_active', checked)}
                      disabled={loading}
                    />
                    <Label htmlFor="is_active" className="cursor-pointer">Active Configuration</Label>
                  </div>
                </div>
              )}
              <div className="col-span-12">
                <SiteTypeManager
                  definitions={nodeTypeDefinitions}
                  onChange={handleNodeTypeDefinitionsChange}
                  onDeleteType={handleConfirmDeleteType}
                  loading={loading}
                  navigationButtons={getNavigationButtons()}
                />
              </div>
            </div>
            {isEditMode && (
              <div className="flex justify-end">
                <Button
                  onClick={handleSaveBasicInfo}
                  disabled={!isBasicStepDirty || loading}
                  leftIcon={<Save className="h-4 w-4" />}
                >
                  Save Basic Information
                </Button>
              </div>
            )}
          </div>
        );
        
      case 1: // Products
        return (
          <ProductForm
            products={products}
            onAdd={handleAddProduct}
            onUpdate={handleUpdateProduct}
            onDelete={handleDeleteProduct}
            loading={loading}
            navigationButtons={getNavigationButtons()}
          />
        );
        
      case 2: // Sites
        return (
          <SiteForm
            sites={sites}
            siteTypeDefinitions={nodeTypeDefinitions}
            onAdd={handleAddSite}
            onUpdate={handleUpdateSite}
            onDelete={handleDeleteSite}
            loading={loading}
            navigationButtons={getNavigationButtons()}
          />
        );

      case 3: // Transportation Lanes (AWS SC DM)
        return (
          <TransportationLaneForm
            lanes={lanes}
            sites={sites}
            siteTypeDefinitions={nodeTypeDefinitions}
            onAdd={handleAddLane}
            onUpdate={handleUpdateLane}
            onDelete={handleDeleteLane}
            loading={loading}
            navigationButtons={getNavigationButtons()}
          />
        );

      case 4: // Product Sourcing
        return (
          <SourcingTreeForm
            products={products}
            sites={sites}
            lanes={lanes}
            markets={markets}
            productSiteConfigs={productSiteConfigs}
            onAdd={handleAddProductSiteConfig}
            onUpdate={handleUpdateProductSiteConfig}
            onDelete={() => {}}
            loading={loading}
            navigationButtons={getNavigationButtons()}
          />
        );

      case 5: // Bill of Materials
        return (
          <BOMForm
            products={products}
            sites={sites}
            onUpdateSite={handleUpdateSite}
            loading={loading}
            navigationButtons={getNavigationButtons()}
          />
        );

      case 6: // Markets
        return (
          <MarketManager
            markets={markets}
            loading={loading}
            onAdd={handleAddMarket}
            onUpdate={handleUpdateMarket}
            onDelete={handleDeleteMarket}
            navigationButtons={getNavigationButtons()}
          />
        );

      case 7: // Market Demands
        return (
          <MarketDemandForm
            demands={marketDemands}
            products={products}
            markets={markets}
            onAdd={handleAddMarketDemand}
            onUpdate={handleUpdateMarketDemand}
            onDelete={handleDeleteMarketDemand}
            loading={loading}
            navigationButtons={getNavigationButtons()}
          />
        );

      case 8: // Review
        return (
          <div>
            <h3 className="text-lg font-semibold mb-4">Review Configuration</h3>
            <Card variant="outline" className="p-6 mb-6">
              <h4 className="font-medium mb-2">Basic Information</h4>
              <p className="text-sm">Name: {formik.values.name}</p>
              <p className="text-sm">Description: {formik.values.description || 'N/A'}</p>
              <p className="text-sm">Time Bucket: {formik.values.time_bucket}</p>
              <p className="text-sm">Status: {formik.values.is_active ? 'Active' : 'Inactive'}</p>
              {allowGroupSelection && (
                <p className="text-sm">Organization ID: {formik.values.tenant_id || (config.tenant_id ? String(config.tenant_id) : 'N/A')}</p>
              )}
            </Card>

            <Card variant="outline" className="p-6 mb-6">
              <h4 className="font-medium mb-2">Products ({products.length})</h4>
              {products.length > 0 ? (
                <ul className="list-disc list-inside">
                  {products.map(product => (
                    <li key={product.id}>{product.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No products configured</p>
              )}
            </Card>

            <Card variant="outline" className="p-6 mb-6">
              <h4 className="font-medium mb-2">Markets ({markets.length})</h4>
              {markets.length > 0 ? (
                <ul className="list-disc list-inside">
                  {markets.map(market => (
                    <li key={market.id}>{market.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No markets defined</p>
              )}
            </Card>

            <Card variant="outline" className="p-6 mb-6">
              <h4 className="font-medium mb-2">Sites ({sites.length})</h4>
              {sites.length > 0 ? (
                <ul className="list-disc list-inside">
                  {sites.map(site => (
                    <li key={site.id} className="flex items-center gap-2">
                      {site.name}{' '}
                      <Badge variant="secondary">
                        {getSiteTypeDisplayName(getSiteDagType(site), nodeTypeDefinitions)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No sites configured</p>
              )}
            </Card>

            <Button
              onClick={handleSubmit}
              disabled={loading}
              leftIcon={loading ? <Spinner size="sm" /> : <Save className="h-4 w-4" />}
            >
              {isEditMode ? 'Update Configuration' : 'Create Configuration'}
            </Button>
          </div>
        );
        
      default:
        return <div>Unknown step</div>;
    }
  };

  // Handler functions for CRUD operations
  const handleAddProduct = async (productData) => {
    try {
      setLoading(true);
      await createProduct(id, productData);
      await fetchProducts();
      enqueueSnackbar('Product added successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error adding product:', err);
      enqueueSnackbar('Failed to add product', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProduct = async (productId, productData) => {
    try {
      setLoading(true);
      await updateProduct(id, productId, productData);
      await fetchProducts();
      enqueueSnackbar('Product updated successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error updating product:', err);
      enqueueSnackbar('Failed to update product', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteProduct = async (productId) => {
    try {
      setLoading(true);
      await deleteProduct(id, productId);
      await fetchProducts();
      enqueueSnackbar('Product deleted successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error deleting product:', err);
      enqueueSnackbar('Failed to delete product', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddSite = async (siteData) => {
    try {
      setLoading(true);
      await createSite(id, siteData);
      await fetchSites();
      enqueueSnackbar('Site added successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error adding site:', err);
      enqueueSnackbar('Failed to add site', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateSite = async (siteId, siteData) => {
    try {
      setLoading(true);
      await updateSite(id, siteId, siteData);
      await fetchSites();
      enqueueSnackbar('Site updated successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error updating site:', err);
      enqueueSnackbar('Failed to update site', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSite = async (siteId) => {
    try {
      setLoading(true);
      await deleteSite(id, siteId);
      await fetchSites();
      enqueueSnackbar('Site deleted successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error deleting site:', err);
      enqueueSnackbar('Failed to delete site', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddLane = async (laneData) => {
    try {
      setLoading(true);
      await createLane(id, laneData);
      await fetchLanes();
      enqueueSnackbar('Lane added successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error adding lane:', err);
      enqueueSnackbar('Failed to add lane', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateLane = async (laneId, laneData) => {
    try {
      setLoading(true);
      await updateLane(id, laneId, laneData);
      await fetchLanes();
      enqueueSnackbar('Lane updated successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error updating lane:', err);
      enqueueSnackbar('Failed to update lane', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteLane = async (laneId) => {
    try {
      setLoading(true);
      await deleteLane(id, laneId);
      await fetchLanes();
      enqueueSnackbar('Lane deleted successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error deleting lane:', err);
      enqueueSnackbar('Failed to delete lane', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddProductSiteConfig = async (configData) => {
    try {
      setLoading(true);
      await createProductSiteConfig(id, configData);
      await fetchProductSiteConfigs();
      enqueueSnackbar('Product-Site configuration added successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error adding product-site config:', err);
      enqueueSnackbar('Failed to add product-site configuration', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProductSiteConfig = async (configId, configData) => {
    try {
      setLoading(true);
      await updateProductSiteConfig(id, configId, configData);
      await fetchProductSiteConfigs();
      enqueueSnackbar('Product-Site configuration updated successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error updating product-site config:', err);
      enqueueSnackbar('Failed to update product-site configuration', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const ensureEditableConfig = () => {
    if (!isEditMode) {
      enqueueSnackbar('Please save the configuration before editing markets or demands.', {
        variant: 'warning',
      });
      return false;
    }
    return true;
  };

  const handleAddMarket = async (marketData) => {
    if (!ensureEditableConfig()) return;
    try {
      setLoading(true);
      await createMarket(id, marketData);
      await Promise.all([fetchMarkets(), fetchMarketDemands()]);
      enqueueSnackbar('Market added successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error adding market:', err);
      enqueueSnackbar(err.response?.data?.detail || 'Failed to add market', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateMarket = async (marketId, marketData) => {
    if (!ensureEditableConfig()) return;
    try {
      setLoading(true);
      await updateMarket(id, marketId, marketData);
      await fetchMarkets();
      enqueueSnackbar('Market updated successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error updating market:', err);
      enqueueSnackbar(err.response?.data?.detail || 'Failed to update market', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteMarket = async (marketId) => {
    if (!ensureEditableConfig()) return;
    try {
      setLoading(true);
      await deleteMarket(id, marketId);
      await Promise.all([fetchMarkets(), fetchMarketDemands()]);
      enqueueSnackbar('Market deleted successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error deleting market:', err);
      enqueueSnackbar(err.response?.data?.detail || 'Failed to delete market', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddMarketDemand = async (demandData) => {
    if (!ensureEditableConfig()) return;
    try {
      setLoading(true);
      await createMarketDemand(id, demandData);
      await fetchMarketDemands();
      enqueueSnackbar('Market demand added successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error adding market demand:', err);
      enqueueSnackbar('Failed to add market demand', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateMarketDemand = async (demandId, demandData) => {
    if (!ensureEditableConfig()) return;
    try {
      setLoading(true);
      await updateMarketDemand(id, demandId, demandData);
      await fetchMarketDemands();
      enqueueSnackbar('Market demand updated successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error updating market demand:', err);
      enqueueSnackbar('Failed to update market demand', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteMarketDemand = async (demandId) => {
    if (!ensureEditableConfig()) return;
    try {
      setLoading(true);
      await deleteMarketDemand(id, demandId);
      await fetchMarketDemands();
      enqueueSnackbar('Market demand deleted successfully', { variant: 'success' });
    } catch (err) {
      console.error('Error deleting market demand:', err);
      enqueueSnackbar('Failed to delete market demand', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = () => {
    formik.handleSubmit();
  };

  if (loading && !isEditMode) {
    return (
      <div className="flex justify-center items-center min-h-[300px]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive" className="mb-6">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
        <div className="flex items-center">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mr-4">
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Go back</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <h1 className="text-xl font-semibold">
            {isEditMode ? 'Edit Configuration' : 'New Configuration'}
          </h1>
        </div>
        <Button variant="outline" onClick={() => navigate(getAdminDashboardPath())}>
          Back to Admin Dashboard
        </Button>
      </div>

      {/* Stepper */}
      <div className="flex flex-wrap justify-center gap-2 mb-8">
        {STEPS.map((label, index) => (
          <button
            key={label}
            onClick={() => handleStep(index)}
            className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
              index === activeStep
                ? 'bg-primary text-primary-foreground'
                : index < activeStep
                  ? 'bg-muted text-foreground cursor-pointer hover:bg-muted/80'
                  : 'bg-muted/50 text-muted-foreground'
            }`}
            disabled={index > activeStep}
          >
            <span className={`flex items-center justify-center w-6 h-6 rounded-full text-xs font-medium ${
              index < activeStep
                ? 'bg-primary/20 text-primary'
                : index === activeStep
                  ? 'bg-primary-foreground/20 text-primary-foreground'
                  : 'bg-muted text-muted-foreground'
            }`}>
              {index < activeStep ? <Check className="h-3 w-3" /> : index + 1}
            </span>
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="pt-6">
          {renderStepContent(activeStep)}
        </CardContent>
      </Card>

      {/* Unsaved Changes Modal */}
      <Modal
        isOpen={basicStepConfirmOpen}
        onClose={handleConfirmCancel}
        title="Unsaved Changes"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleConfirmDiscard}>Discard</Button>
            <Button variant="outline" onClick={handleConfirmCancel}>Cancel</Button>
            <Button onClick={handleConfirmSave} disabled={loading}>
              Save & Continue
            </Button>
          </div>
        }
      >
        <p className="text-sm text-muted-foreground">
          Save your Basic Information changes before continuing to the next step, or discard them to revert.
        </p>
      </Modal>

      {/* Delete Type Confirmation Modal */}
      <Modal
        isOpen={confirmDeleteType.open}
        onClose={handleDeleteTypeCancel}
        title="Delete DAG/Group Type?"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleDeleteTypeCancel}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={handleDeleteTypeConfirm}
              disabled={loading}
            >
              Delete type and sites
            </Button>
          </div>
        }
      >
        <p className="text-sm text-muted-foreground">
          {`Sites with type "${confirmDeleteType.definition?.label || confirmDeleteType.definition?.type}" exist (${confirmDeleteType.sites.length}). Delete the sites and this DAG/Group type?`}
        </p>
      </Modal>

      <div className="flex justify-between mt-6">
        <Button
          variant="outline"
          onClick={handleBack}
          disabled={loading}
          leftIcon={<ArrowLeft className="h-4 w-4" />}
        >
          {activeStep === 0 ? 'Back to List' : 'Back'}
        </Button>

        {activeStep < STEPS.length - 1 && (
          <Button
            onClick={handleNext}
            disabled={loading}
            rightIcon={loading ? <Spinner size="sm" /> : null}
          >
            Next
          </Button>
        )}
      </div>
    </div>
  );
};

export default SupplyChainConfigForm;
