import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FaBuilding, FaCheck, FaEdit, FaPlus, FaSave, FaSpinner, FaTimes, FaTrash } from 'react-icons/fa';
import { api } from '../../services/api';
import { toast } from 'react-toastify';

const DEFAULT_FORM = {
  name: 'Autonomy',
  description: '',
  logo: '/autonomy_logo.svg',
  admin: {
    username: 'tenantadmin',
    email: 'tenantadmin@autonomy.ai',
    password: 'Autonomy@2026',
    full_name: 'Tenant Administrator',
  },
};

const createDefaultForm = () => ({
  ...DEFAULT_FORM,
  admin: { ...DEFAULT_FORM.admin },
});

const TenantManagement = () => {
  const [tenants, setTenants] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [savingCustomer, setSavingCustomer] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTenantId, setEditingTenantId] = useState(null);
  const [form, setForm] = useState(createDefaultForm());
  const [logoPreview, setLogoPreview] = useState(DEFAULT_FORM.logo || '');
  const [logoFileName, setLogoFileName] = useState('');
  const [saving, setSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [autoCreation, setAutoCreation] = useState({ open: false, step: 0, completed: false, error: null });
  const autoCreationRequestedRef = useRef(false);

  const AUTO_CREATION_STEPS = [
    'Creating default users\u2026',
    'Creating supply chain configuration\u2026',
    'Creating scenario\u2026',
  ];

  const selectedCustomer = useMemo(
    () => customers.find((c) => c.id === selectedCustomerId) || null,
    [customers, selectedCustomerId]
  );

  // Tenants belonging to the selected customer
  const selectedCustomerTenants = useMemo(() => {
    if (!selectedCustomer) return [];
    const ids = new Set();
    if (selectedCustomer.production_tenant_id) ids.add(selectedCustomer.production_tenant_id);
    if (selectedCustomer.learning_tenant_id) ids.add(selectedCustomer.learning_tenant_id);
    // Production first, then learning
    return tenants
      .filter((t) => ids.has(t.id))
      .sort((a, b) => {
        const aIsProd = a.id === selectedCustomer.production_tenant_id;
        const bIsProd = b.id === selectedCustomer.production_tenant_id;
        if (aIsProd && !bIsProd) return -1;
        if (!aIsProd && bIsProd) return 1;
        return 0;
      });
  }, [selectedCustomer, tenants]);

  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const triggerAutoCreateDefaultTenant = useCallback(async () => {
    if (autoCreationRequestedRef.current) return;
    autoCreationRequestedRef.current = true;
    setAutoCreation({ open: true, step: 0, completed: false, error: null });
    try {
      setAutoCreation((prev) => ({ ...prev, step: 0 }));
      await delay(300);
      setAutoCreation((prev) => ({ ...prev, step: 1 }));
      await api.post('/tenants/default');
      setAutoCreation((prev) => ({ ...prev, step: 2 }));
      await delay(300);
      setAutoCreation((prev) => ({ ...prev, completed: true }));
      toast.success('Default Autonomy customer created successfully');
      await delay(600);
      setAutoCreation((prev) => ({ ...prev, open: false }));
    } catch (error) {
      console.error('Failed to auto-create default customer:', error);
      const detail = error?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : detail?.message || 'Failed to create default customer. Please try again.';
      setAutoCreation({ open: true, step: 0, completed: false, error: message });
      toast.error(message);
      autoCreationRequestedRef.current = false;
    }
  }, []);

  const dismissAutoCreationError = useCallback(() => {
    autoCreationRequestedRef.current = false;
    setAutoCreation({ open: false, step: 0, completed: false, error: null });
  }, []);

  const fetchData = useCallback(
    async (nextCustomerId = null) => {
      setIsLoading(true);
      try {
        const [tenantsRes, customersRes] = await Promise.all([
          api.get('/tenants'),
          api.get('/customers').catch(() => ({ data: [] })),
        ]);
        const tenantData = Array.isArray(tenantsRes.data) ? tenantsRes.data : [];
        const customerData = Array.isArray(customersRes.data) ? customersRes.data : [];
        setTenants(tenantData);
        setCustomers(customerData);

        if (tenantData.length === 0) {
          setSelectedCustomerId(null);
          await triggerAutoCreateDefaultTenant();
          return;
        }

        if (nextCustomerId && customerData.some((c) => c.id === nextCustomerId)) {
          setSelectedCustomerId(nextCustomerId);
        } else {
          setSelectedCustomerId((prev) =>
            prev && customerData.some((c) => c.id === prev) ? prev : customerData[0]?.id || null
          );
        }
      } catch (error) {
        console.error('Failed to load data:', error);
        setTenants([]);
        setCustomers([]);
        toast.error('Failed to load data.');
      } finally {
        setIsLoading(false);
      }
    },
    [triggerAutoCreateDefaultTenant]
  );

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Customer editing (inline) ──────────────────────────────────────
  const startEditingCustomer = useCallback(() => {
    if (!selectedCustomer) return;
    setEditingCustomer({
      contact_name: selectedCustomer.contact_name || '',
      contact_email: selectedCustomer.contact_email || '',
      contact_phone: selectedCustomer.contact_phone || '',
      industry: selectedCustomer.industry || '',
      website: selectedCustomer.website || '',
      contract_start_date: selectedCustomer.contract_start_date || '',
      contract_end_date: selectedCustomer.contract_end_date || '',
      contract_notes: selectedCustomer.contract_notes || '',
    });
  }, [selectedCustomer]);

  const cancelEditingCustomer = useCallback(() => {
    setEditingCustomer(null);
  }, []);

  const saveCustomer = useCallback(async () => {
    if (!selectedCustomer || !editingCustomer) return;
    setSavingCustomer(true);
    try {
      await api.put(`/customers/${selectedCustomer.id}`, editingCustomer);
      toast.success('Customer updated');
      setEditingCustomer(null);
      await fetchData(selectedCustomer.id);
    } catch (error) {
      console.error('Failed to update customer:', error);
      toast.error('Failed to update customer.');
    } finally {
      setSavingCustomer(false);
    }
  }, [selectedCustomer, editingCustomer, fetchData]);

  const handleCustomerFieldChange = (field, value) => {
    setEditingCustomer((prev) => ({ ...prev, [field]: value }));
  };

  // ── Tenant create/edit modal ───────────────────────────────────────
  const openModal = useCallback((tenant = null) => {
    if (tenant) {
      setEditingTenantId(tenant.id);
      const adminUser = tenant.admin || {};
      setForm({
        name: tenant.name || '',
        description: tenant.description || '',
        logo: tenant.logo || '',
        admin: {
          username: adminUser.username || '',
          email: adminUser.email || '',
          password: '',
          full_name: adminUser.full_name || '',
        },
      });
      setLogoPreview(tenant.logo || '');
    } else {
      setEditingTenantId(null);
      const defaults = createDefaultForm();
      setForm(defaults);
      setLogoPreview(defaults.logo || '');
    }
    setLogoFileName('');
    setIsModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setIsModalOpen(false);
    setSaving(false);
    setEditingTenantId(null);
    const defaults = createDefaultForm();
    setForm(defaults);
    setLogoPreview(defaults.logo || '');
    setLogoFileName('');
  }, []);

  const handleChange = (event) => {
    const { name, value } = event.target;
    if (name.startsWith('admin.')) {
      const key = name.split('.')[1];
      setForm((prev) => ({ ...prev, admin: { ...prev.admin, [key]: value } }));
      return;
    }
    if (name === 'logo') {
      setLogoFileName('');
      setLogoPreview(value);
    }
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleLogoFileChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      setForm((prev) => ({ ...prev, logo: result }));
      setLogoPreview(result);
      setLogoFileName(file.name);
    };
    reader.readAsDataURL(file);
    event.target.value = '';
  };

  const handleRemoveLogo = () => {
    setLogoFileName('');
    setForm((prev) => ({ ...prev, logo: '' }));
    setLogoPreview('');
  };

  const handleSubmit = async (event) => {
    event?.preventDefault();
    const trimmedName = form.name.trim();
    if (!trimmedName) {
      toast.error('Customer name is required.');
      return;
    }
    setSaving(true);
    try {
      if (editingTenantId) {
        await api.put(`/tenants/${editingTenantId}`, {
          name: trimmedName,
          description: form.description,
          logo: form.logo,
        });
        toast.success('Tenant updated successfully');
        closeModal();
        await fetchData(selectedCustomerId);
      } else {
        await api.post('/tenants', { ...form, name: trimmedName });
        toast.success('Customer created successfully');
        closeModal();
        await fetchData();
      }
    } catch (error) {
      console.error('Failed to save:', error);
      toast.error('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // ── Delete ─────────────────────────────────────────────────────────
  const closeDeleteModal = useCallback(() => {
    if (deleting) return;
    setDeleteTarget(null);
  }, [deleting]);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/tenants/${deleteTarget.id}`);
      toast.success('Tenant deleted');
      setDeleteTarget(null);
      await fetchData(selectedCustomerId);
    } catch (error) {
      console.error('Failed to delete tenant:', error);
      toast.error('Failed to delete tenant.');
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget, fetchData, selectedCustomerId]);

  // ── Render ─────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-800">Tenant Management</h1>
        <button
          type="button"
          onClick={() => openModal(null)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          <FaPlus /> Add Customer
        </button>
      </div>

      {customers.length === 0 ? (
        <div className="table-surface p-8 text-center">
          <h2 className="text-lg font-semibold text-gray-800">No customers yet</h2>
          <p className="mt-2 text-sm text-gray-600">Add your first customer to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ── LEFT: Customer list ───────────────────────────────── */}
          <div className="lg:col-span-1">
            <div className="table-surface overflow-hidden rounded-lg">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Autonomy Customers</h2>
              </div>
              <ul className="divide-y divide-gray-200">
                {customers.map((customer) => {
                  const isSelected = customer.id === selectedCustomerId;
                  return (
                    <li
                      key={customer.id}
                      onClick={() => { setSelectedCustomerId(customer.id); setEditingCustomer(null); }}
                      className={`px-4 py-3 cursor-pointer transition-colors ${
                        isSelected ? 'bg-blue-50 border-l-4 border-blue-500' : 'hover:bg-gray-50 border-l-4 border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <FaBuilding className={`text-lg ${isSelected ? 'text-blue-600' : 'text-gray-400'}`} />
                        <div className="min-w-0">
                          <div className={`text-sm font-medium truncate ${isSelected ? 'text-blue-900' : 'text-gray-900'}`}>
                            {customer.name}
                          </div>
                          {customer.industry ? (
                            <div className="text-xs text-gray-500 truncate">{customer.industry}</div>
                          ) : null}
                          <div className="flex gap-1.5 mt-1">
                            {customer.production_tenant_id ? (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">PROD</span>
                            ) : null}
                            {customer.learning_tenant_id ? (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-100 text-purple-700">LEARN</span>
                            ) : null}
                            {!customer.is_active ? (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-700">INACTIVE</span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          {/* ── RIGHT: Customer detail + Tenants ──────────────────── */}
          <div className="lg:col-span-2 space-y-6">
            {selectedCustomer ? (
              <>
                {/* Customer details card */}
                <div className="table-surface rounded-lg overflow-hidden">
                  <div className="px-6 py-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-gray-800">{selectedCustomer.name}</h2>
                    <div className="flex gap-2">
                      {editingCustomer ? (
                        <>
                          <button type="button" onClick={cancelEditingCustomer} className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50">
                            <FaTimes /> Cancel
                          </button>
                          <button type="button" onClick={saveCustomer} disabled={savingCustomer} className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
                            <FaSave /> {savingCustomer ? 'Saving\u2026' : 'Save'}
                          </button>
                        </>
                      ) : (
                        <button type="button" onClick={startEditingCustomer} className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50">
                          <FaEdit /> Edit
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="px-6 py-4">
                    {selectedCustomer.description ? (
                      <p className="text-sm text-gray-600 mb-4">{selectedCustomer.description}</p>
                    ) : null}
                    {editingCustomer ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Contact Name</label>
                          <input type="text" value={editingCustomer.contact_name} onChange={(e) => handleCustomerFieldChange('contact_name', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Contact Email</label>
                          <input type="email" value={editingCustomer.contact_email} onChange={(e) => handleCustomerFieldChange('contact_email', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Contact Phone</label>
                          <input type="text" value={editingCustomer.contact_phone} onChange={(e) => handleCustomerFieldChange('contact_phone', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Industry</label>
                          <input type="text" value={editingCustomer.industry} onChange={(e) => handleCustomerFieldChange('industry', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Website</label>
                          <input type="url" value={editingCustomer.website} onChange={(e) => handleCustomerFieldChange('website', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Contract Start</label>
                          <input type="date" value={editingCustomer.contract_start_date} onChange={(e) => handleCustomerFieldChange('contract_start_date', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500 mb-1">Contract End</label>
                          <input type="date" value={editingCustomer.contract_end_date} onChange={(e) => handleCustomerFieldChange('contract_end_date', e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                        <div className="md:col-span-2">
                          <label className="block text-xs font-medium text-gray-500 mb-1">Contract Notes</label>
                          <textarea value={editingCustomer.contract_notes} onChange={(e) => handleCustomerFieldChange('contract_notes', e.target.value)} rows={2}
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <div className="text-xs font-medium text-gray-500">Contact</div>
                          <div className="text-gray-900">{selectedCustomer.contact_name || '\u2014'}</div>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-500">Email</div>
                          <div className="text-gray-900">{selectedCustomer.contact_email || '\u2014'}</div>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-500">Phone</div>
                          <div className="text-gray-900">{selectedCustomer.contact_phone || '\u2014'}</div>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-500">Industry</div>
                          <div className="text-gray-900">{selectedCustomer.industry || '\u2014'}</div>
                        </div>
                        {selectedCustomer.website ? (
                          <div>
                            <div className="text-xs font-medium text-gray-500">Website</div>
                            <div className="text-blue-600 truncate">{selectedCustomer.website}</div>
                          </div>
                        ) : null}
                        {selectedCustomer.contract_start_date || selectedCustomer.contract_end_date ? (
                          <div className="col-span-2">
                            <div className="text-xs font-medium text-gray-500">Contract Period</div>
                            <div className="text-gray-900">
                              {selectedCustomer.contract_start_date || '?'} &mdash; {selectedCustomer.contract_end_date || 'ongoing'}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )}
                  </div>
                </div>

                {/* Tenants table */}
                <div className="table-surface overflow-hidden rounded-lg">
                  <div className="px-6 py-3 bg-gray-50 border-b border-gray-200">
                    <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Tenants</h3>
                  </div>
                  {selectedCustomerTenants.length === 0 ? (
                    <div className="px-6 py-6 text-center text-sm text-gray-500">No tenants found for this customer.</div>
                  ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tenant</th>
                          <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mode</th>
                          <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tenant Admin</th>
                          <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {selectedCustomerTenants.map((tenant) => {
                          const adminName = tenant.admin?.full_name || tenant.admin?.username || '\u2014';
                          const adminEmail = tenant.admin?.email;
                          const mode = tenant.mode || 'production';
                          const isLearning = mode === 'learning';
                          return (
                            <tr key={tenant.id} className="hover:bg-gray-50">
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="text-sm font-medium text-gray-900">{tenant.name || '\u2014'}</div>
                                {tenant.description ? (
                                  <div className="text-sm text-gray-500 mt-0.5">{tenant.description}</div>
                                ) : null}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                  isLearning ? 'bg-purple-100 text-purple-800' : 'bg-green-100 text-green-800'
                                }`}>
                                  {isLearning ? 'Learning' : 'Production'}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="text-sm font-medium text-gray-900">{adminName}</div>
                                {adminEmail ? <div className="text-sm text-gray-500">{adminEmail}</div> : null}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-right">
                                <div className="flex justify-end gap-2">
                                  <button type="button" onClick={() => openModal(tenant)}
                                    className="text-gray-500 hover:text-blue-600 p-1" title="Edit tenant">
                                    <FaEdit />
                                  </button>
                                  <button type="button" onClick={() => { setDeleteTarget(tenant); setDeleting(false); }}
                                    className="text-gray-500 hover:text-red-600 p-1" title="Delete tenant">
                                    <FaTrash />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            ) : (
              <div className="table-surface p-8 text-center rounded-lg">
                <FaBuilding className="mx-auto text-4xl text-gray-300 mb-3" />
                <h2 className="text-lg font-semibold text-gray-800">Select a customer</h2>
                <p className="mt-1 text-sm text-gray-500">Choose a customer from the list to view their tenants.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Create customer / Edit tenant modal ─────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-800">
                {editingTenantId ? 'Edit Tenant' : 'Add New Customer'}
              </h2>
              <button type="button" onClick={closeModal} className="text-gray-500 hover:text-gray-700">{'\u2715'}</button>
            </div>

            <form onSubmit={handleSubmit} className="px-6 py-6 space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="tenant-name">Customer Name</label>
                <input id="tenant-name" name="name" type="text" value={form.name} onChange={handleChange} required
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="tenant-description">Description</label>
                <textarea id="tenant-description" name="description" value={form.description} onChange={handleChange} rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Add a short description for this customer" />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="tenant-logo">Customer Logo</label>
                <input id="tenant-logo" name="logo" type="text" value={form.logo || ''} onChange={handleChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Paste a logo URL or upload a file below" />
                <div className="flex flex-wrap items-center gap-3 mt-2">
                  <label className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white cursor-pointer hover:bg-gray-50">
                    <input type="file" accept="image/*" className="hidden" onChange={handleLogoFileChange} />
                    Upload Logo
                  </label>
                  <span className="text-sm text-gray-500">
                    {logoFileName ? `Selected file: ${logoFileName}` : 'Upload an image (PNG, JPG, SVG) or provide a URL above.'}
                  </span>
                  {logoPreview ? (
                    <button type="button" onClick={handleRemoveLogo} className="text-sm text-red-600 hover:text-red-800">Remove</button>
                  ) : null}
                </div>
                {logoPreview ? (
                  <div className="mt-3 flex items-center gap-4">
                    <img src={logoPreview} alt="Logo preview" className="h-20 w-20 rounded-md object-contain border border-gray-200 bg-gray-50 p-2" />
                    <p className="text-sm text-gray-500">Preview of the logo that will be saved for this customer.</p>
                  </div>
                ) : null}
              </div>

              {!editingTenantId && (
                <>
                  <div className="bg-blue-50 border border-blue-200 rounded-md px-4 py-3">
                    <p className="text-sm text-blue-800 font-medium">Two tenants will be created:</p>
                    <ul className="mt-1 text-sm text-blue-700 list-disc list-inside">
                      <li><strong>Production</strong> &mdash; {form.name || 'Customer'} &mdash; admin: {form.admin.email || 'admin@domain.com'}</li>
                      <li><strong>Learning</strong> &mdash; {form.name || 'Customer'} (Learning) &mdash; admin: {form.admin.email ? `${form.admin.email.split('@')[0]}_learn@${form.admin.email.split('@')[1] || 'domain.com'}` : 'admin_learn@domain.com'}</li>
                    </ul>
                    <p className="mt-1 text-xs text-blue-600">Both admins share the same password. The learning admin uses the same credentials with &ldquo;_learn&rdquo; appended to username and email local part.</p>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-username">Production Admin Username</label>
                      <input id="admin-username" name="admin.username" type="text" value={form.admin.username} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-email">Production Admin Email</label>
                      <input id="admin-email" name="admin.email" type="email" value={form.admin.email} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-full-name">Production Admin Full Name</label>
                      <input id="admin-full-name" name="admin.full_name" type="text" value={form.admin.full_name} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-password">Admin Password</label>
                      <input id="admin-password" name="admin.password" type="password" value={form.admin.password} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                  </div>
                </>
              )}

              {editingTenantId && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Supply Chain Configurations</label>
                  <p className="text-sm text-gray-500 px-3 py-2 border border-gray-200 rounded-md bg-gray-50">
                    Supply chain configurations can be managed in the Supply Chain Config page.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
                <button type="button" onClick={closeModal} disabled={saving}
                  className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button type="submit" disabled={saving}
                  className={`px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 ${saving ? 'opacity-75 cursor-not-allowed' : ''}`}>
                  {saving ? 'Saving\u2026' : editingTenantId ? 'Save Changes' : 'Create Customer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Delete confirmation ──────────────────────────────────────── */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-800">Delete Tenant</h2>
            </div>
            <div className="px-6 py-6">
              <p className="text-sm text-gray-700">
                Are you sure you want to delete <span className="font-semibold">{deleteTarget.name || 'this tenant'}</span>?
                This action cannot be undone and will remove all associated supply chain configurations, scenarios, and users.
              </p>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <button type="button" onClick={closeDeleteModal} disabled={deleting}
                className={`px-4 py-2 rounded-md text-sm font-medium border border-gray-300 text-gray-700 hover:bg-gray-50 ${deleting ? 'opacity-75 cursor-not-allowed' : ''}`}>
                Cancel
              </button>
              <button type="button" onClick={handleConfirmDelete} disabled={deleting}
                className={`px-4 py-2 rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700 ${deleting ? 'opacity-75 cursor-not-allowed' : ''}`}>
                {deleting ? 'Deleting\u2026' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Auto-creation overlay ────────────────────────────────────── */}
      {autoCreation.open && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-800">Creating default Autonomy customer{'\u2026'}</h2>
            <ul className="space-y-2 text-sm text-gray-700">
              {AUTO_CREATION_STEPS.map((step, index) => {
                const isActive = index === autoCreation.step;
                const isCompleted = autoCreation.completed && index <= autoCreation.step;
                return (
                  <li key={step} className="flex items-center gap-2">
                    {isCompleted ? (
                      <FaCheck className="text-emerald-600" />
                    ) : isActive ? (
                      <FaSpinner className="animate-spin text-blue-500" />
                    ) : (
                      <span className="h-3 w-3 rounded-full bg-gray-300" />
                    )}
                    <span>{step}</span>
                  </li>
                );
              })}
            </ul>
            {autoCreation.error ? (
              <div className="flex items-center justify-between pt-3">
                <p className="text-sm text-red-600">{autoCreation.error}</p>
                <button type="button" onClick={dismissAutoCreationError}
                  className="px-3 py-1 rounded-md text-sm font-medium bg-red-500 text-white hover:bg-red-600">
                  Dismiss
                </button>
              </div>
            ) : (
              <p className="text-xs text-gray-500">This may take a few moments{'\u2026'}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantManagement;
