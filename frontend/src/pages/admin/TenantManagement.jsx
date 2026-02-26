import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FaCheck, FaEdit, FaPlus, FaSpinner, FaTrash } from 'react-icons/fa';
import { api } from '../../services/api';
import { toast } from 'react-toastify';

const DEFAULT_FORM = {
  name: 'Autonomy',
  description: '',
  logo: '/autonomy_logo.svg',
  admin: {
    username: 'groupadmin',
    email: 'groupadmin@autonomy.ai',
    password: 'Autonomy@2025',
    full_name: 'Organization Administrator',
  },
};

const createDefaultForm = () => ({
  ...DEFAULT_FORM,
  admin: { ...DEFAULT_FORM.admin },
});

const TenantManagement = () => {
  const [tenants, setTenants] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState(null);
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

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === selectedTenantId) || null,
    [tenants, selectedTenantId]
  );

  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const triggerAutoCreateDefaultTenant = useCallback(async () => {
    if (autoCreationRequestedRef.current) {
      return;
    }

    autoCreationRequestedRef.current = true;
    setAutoCreation({ open: true, step: 0, completed: false, error: null });

    try {
      setAutoCreation((prev) => ({ ...prev, step: 0 }));
      await delay(300);
      setAutoCreation((prev) => ({ ...prev, step: 1 }));

      const response = await api.post('/tenants/default');
      const createdTenant = response?.data || response;

      setAutoCreation((prev) => ({ ...prev, step: 2 }));
      await delay(300);
      setAutoCreation((prev) => ({ ...prev, completed: true }));
      toast.success('Default Autonomy organization created successfully');

      if (createdTenant) {
        const listResponse = await api.get('/tenants');
        const createdTenants = Array.isArray(listResponse.data) ? listResponse.data : [];
        setTenants(createdTenants);
        setSelectedTenantId(createdTenants[0]?.id || null);
      }

      await delay(600);
      setAutoCreation((prev) => ({ ...prev, open: false }));
    } catch (error) {
      console.error('Failed to auto-create default organization:', error);
      const detail = error?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : detail?.message || 'Failed to create default organization. Please try again.';
      setAutoCreation({ open: true, step: 0, completed: false, error: message });
      toast.error(message);
      autoCreationRequestedRef.current = false;
    }
  }, []);


  const dismissAutoCreationError = useCallback(() => {
    autoCreationRequestedRef.current = false;
    setAutoCreation({ open: false, step: 0, completed: false, error: null });
  }, []);

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

  const fetchTenants = useCallback(
    async (nextSelectedId = null) => {
      setIsLoading(true);
      try {
        const response = await api.get('/tenants');
        const data = Array.isArray(response.data) ? response.data : [];
        setTenants(data);

        if (data.length === 0) {
          setSelectedTenantId(null);
          await triggerAutoCreateDefaultTenant();
          return;
        }

        if (nextSelectedId && data.some((tenant) => tenant.id === nextSelectedId)) {
          setSelectedTenantId(nextSelectedId);
        } else {
          setSelectedTenantId((prev) =>
            prev && data.some((tenant) => tenant.id === prev) ? prev : data[0]?.id || null
          );
        }
      } catch (error) {
        console.error('Failed to load organizations:', error);
        setTenants([]);
        toast.error('Failed to load organizations.');
      } finally {
        setIsLoading(false);
      }
    },
    [triggerAutoCreateDefaultTenant]
  );

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  const handleChange = (event) => {
    const { name, value } = event.target;

    if (name.startsWith('admin.')) {
      const key = name.split('.')[1];
      setForm((prev) => ({
        ...prev,
        admin: {
          ...prev.admin,
          [key]: value,
        },
      }));
      return;
    }

    if (name === 'logo') {
      setLogoFileName('');
      setLogoPreview(value);
    }

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
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
      toast.error('Organization name is required.');
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
        toast.success('Organization updated successfully');
        closeModal();
        await fetchTenants(editingTenantId);
      } else {
        const { data } = await api.post('/tenants', {
          ...form,
          name: trimmedName,
        });
        toast.success('Organization created successfully');
        closeModal();
        await fetchTenants(data?.id);
      }
    } catch (error) {
      console.error('Failed to save organization:', error);
      toast.error('Failed to save organization. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleEditSelected = () => {
    if (!selectedTenant) return;
    openModal(selectedTenant);
  };

  const handleRequestDeleteSelected = () => {
    if (!selectedTenant) return;
    setDeleteTarget(selectedTenant);
    setDeleting(false);
  };

  const closeDeleteModal = useCallback(() => {
    if (deleting) return;
    setDeleteTarget(null);
  }, [deleting]);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) return;

    setDeleting(true);
    const tenantId = deleteTarget.id;

    try {
      await api.delete(`/tenants/${tenantId}`);
      toast.success('Organization deleted');
      setDeleteTarget(null);
      setSelectedTenantId((prev) => (prev === tenantId ? null : prev));
      await fetchTenants();
    } catch (error) {
      console.error('Failed to delete organization:', error);
      toast.error('Failed to delete organization. Please try again.');
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget, fetchTenants]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-800">Organization Management</h1>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => openModal(null)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
          >
            <FaPlus /> Add Organization
          </button>
          <button
            type="button"
            onClick={handleEditSelected}
            disabled={!selectedTenant}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              selectedTenant
                ? 'border border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
                : 'border border-gray-200 text-gray-400 bg-gray-100 cursor-not-allowed'
            }`}
          >
            <FaEdit /> Edit Organization
          </button>
          <button
            type="button"
            onClick={handleRequestDeleteSelected}
            disabled={!selectedTenant}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              selectedTenant
                ? 'border border-red-200 text-red-600 bg-white hover:bg-red-50'
                : 'border border-gray-200 text-gray-400 bg-gray-100 cursor-not-allowed'
            }`}
          >
            <FaTrash /> Delete Organization
          </button>
        </div>
      </div>

      {tenants.length === 0 ? (
        <div className="table-surface p-8 text-center">
          <h2 className="text-lg font-semibold text-gray-800">No organizations yet</h2>
          <p className="mt-2 text-sm text-gray-600">
            Create your first organization to get started.
          </p>
        </div>
      ) : (
        <>
          <div className="table-surface overflow-hidden sm:rounded-lg">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Organization
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Organization Admin
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {tenants.map((tenant) => {
                    const isSelected = tenant.id === selectedTenantId;
                    const adminName =
                      tenant.admin?.full_name || tenant.admin?.username || '\u2014';
                    const adminEmail = tenant.admin?.email;

                    return (
                      <tr
                        key={tenant.id}
                        onClick={() => setSelectedTenantId(tenant.id)}
                        onDoubleClick={() => openModal(tenant)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'
                        }`}
                        aria-selected={isSelected}
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">
                            {tenant.name || '\u2014'}
                          </div>
                          {tenant.description ? (
                            <div className="text-sm text-gray-500 mt-1">
                              {tenant.description}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">
                            {adminName}
                          </div>
                          {adminEmail ? (
                            <div className="text-sm text-gray-500">{adminEmail}</div>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <p className="mt-3 text-sm text-gray-500">
            Select an organization to enable editing or deletion.
          </p>
        </>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-800">
                {editingTenantId ? 'Edit Organization' : 'Add New Organization'}
              </h2>
              <button
                type="button"
                onClick={closeModal}
                className="text-gray-500 hover:text-gray-700"
              >
                \u2715
              </button>
            </div>

            <form onSubmit={handleSubmit} className="px-6 py-6 space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="tenant-name">
                  Organization Name
                </label>
                <input
                  id="tenant-name"
                  name="name"
                  type="text"
                  value={form.name}
                  onChange={handleChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="tenant-description">
                  Description
                </label>
                <textarea
                  id="tenant-description"
                  name="description"
                  value={form.description}
                  onChange={handleChange}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Add a short description for this organization"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="tenant-logo">
                  Organization Logo
                </label>
                <input
                  id="tenant-logo"
                  name="logo"
                  type="text"
                  value={form.logo || ''}
                  onChange={handleChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Paste a logo URL or upload a file below"
                />
                <div className="flex flex-wrap items-center gap-3 mt-2">
                  <label className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white cursor-pointer hover:bg-gray-50">
                    <input type="file" accept="image/*" className="hidden" onChange={handleLogoFileChange} />
                    Upload Logo
                  </label>
                  <span className="text-sm text-gray-500">
                    {logoFileName
                      ? `Selected file: ${logoFileName}`
                      : 'Upload an image (PNG, JPG, SVG) or provide a URL above.'}
                  </span>
                  {logoPreview && (
                    <button
                      type="button"
                      onClick={handleRemoveLogo}
                      className="text-sm text-red-600 hover:text-red-800"
                    >
                      Remove
                    </button>
                  )}
                </div>
                {logoPreview && (
                  <div className="mt-3 flex items-center gap-4">
                    <img
                      src={logoPreview}
                      alt="Logo preview"
                      className="h-20 w-20 rounded-md object-contain border border-gray-200 bg-gray-50 p-2"
                    />
                    <p className="text-sm text-gray-500">
                      Preview of the logo that will be saved for this organization.
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Supply Chain Configurations
                </label>
                <p className="text-sm text-gray-500 px-3 py-2 border border-gray-200 rounded-md bg-gray-50">
                  {editingTenantId
                    ? 'Supply chain configurations can be managed in the Supply Chain Config page after the organization is created.'
                    : 'A default supply chain configuration will be created with this organization.'}
                </p>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="md:col-span-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-username">
                    Admin Username
                  </label>
                  <input
                    id="admin-username"
                    name="admin.username"
                    type="text"
                    value={form.admin.username}
                    onChange={handleChange}
                    disabled={Boolean(editingTenantId)}
                    className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                      editingTenantId ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''
                    }`}
                  />
                </div>
                <div className="md:col-span-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-email">
                    Admin Email
                  </label>
                  <input
                    id="admin-email"
                    name="admin.email"
                    type="email"
                    value={form.admin.email}
                    onChange={handleChange}
                    disabled={Boolean(editingTenantId)}
                    className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                      editingTenantId ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''
                    }`}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-full-name">
                    Admin Full Name
                  </label>
                  <input
                    id="admin-full-name"
                    name="admin.full_name"
                    type="text"
                    value={form.admin.full_name}
                    onChange={handleChange}
                    disabled={Boolean(editingTenantId)}
                    className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                      editingTenantId ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''
                    }`}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="admin-password">
                    Admin Password
                  </label>
                  <input
                    id="admin-password"
                    name="admin.password"
                    type="password"
                    value={form.admin.password}
                    onChange={handleChange}
                    disabled={Boolean(editingTenantId)}
                    placeholder={editingTenantId ? 'Admin password management is handled separately' : ''}
                    className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                      editingTenantId ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''
                    }`}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className={`px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 ${
                    saving ? 'opacity-75 cursor-not-allowed' : ''
                  }`}
                  disabled={saving}
                >
                  {saving ? 'Saving\u2026' : editingTenantId ? 'Save Changes' : 'Create Organization'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-800">Delete Organization</h2>
            </div>
            <div className="px-6 py-6 space-y-4">
              <p className="text-sm text-gray-700">
                Are you sure you want to delete{' '}
                <span className="font-semibold">{deleteTarget.name || 'this organization'}</span>? This action cannot be undone and
                will remove all associated supply chain configurations, scenarios, and users.
              </p>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <button
                type="button"
                onClick={closeDeleteModal}
                disabled={deleting}
                className={`px-4 py-2 rounded-md text-sm font-medium border border-gray-300 text-gray-700 hover:bg-gray-50 ${
                  deleting ? 'opacity-75 cursor-not-allowed' : ''
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={deleting}
                className={`px-4 py-2 rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700 ${
                  deleting ? 'opacity-75 cursor-not-allowed' : ''
                }`}
              >
                {deleting ? 'Deleting\u2026' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {autoCreation.open && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-800">Creating default Autonomy organization\u2026</h2>
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
                <button
                  type="button"
                  onClick={dismissAutoCreationError}
                  className="px-3 py-1 rounded-md text-sm font-medium bg-red-500 text-white hover:bg-red-600"
                >
                  Dismiss
                </button>
              </div>
            ) : (
              <p className="text-xs text-gray-500">This may take a few moments\u2026</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantManagement;
