import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  Input,
  Label,
  Modal,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/common';
import { Plus, Trash2, Pencil } from 'lucide-react';
import { toast } from 'react-toastify';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { isSystemAdmin as isSystemAdminUser, getUserType as resolveUserType } from '../../utils/authUtils';

const BASE_FORM = {
  username: '',
  email: '',
  password: '',
  tenantId: '',
};

const parseErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object') {
    return detail.message || fallback;
  }
  return fallback;
};

function SystemAdminUserManagement() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const systemAdmin = isSystemAdminUser(user);

  const [admins, setAdmins] = useState([]);
  const [organizations, setOrganizations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ ...BASE_FORM });

  useEffect(() => {
    if (!systemAdmin) {
      navigate('/unauthorized');
    }
  }, [systemAdmin, navigate]);

  const loadOrganizations = useCallback(async () => {
    try {
      const response = await api.get('/tenants');
      const data = Array.isArray(response.data) ? response.data : [];
      setOrganizations(data);
      return data;
    } catch (error) {
      console.error('Error loading organizations:', error);
      setOrganizations([]);
      throw error;
    }
  }, []);

  const loadAdmins = useCallback(async () => {
    try {
      const response = await api.get('/users', { params: { user_type: 'TENANT_ADMIN', limit: 250 } });
      const data = Array.isArray(response.data) ? response.data : [];
      const filtered = data.filter((item) => resolveUserType(item) === 'tenantadmin');
      setAdmins(filtered);
      return filtered;
    } catch (error) {
      console.error('Error loading organization administrators:', error);
      setAdmins([]);
      throw error;
    }
  }, []);

  useEffect(() => {
    if (!systemAdmin) {
      return;
    }

    const fetchAll = async () => {
      setLoading(true);
      try {
        await Promise.all([loadOrganizations(), loadAdmins()]);
      } catch (error) {
        toast.error('Failed to load user information');
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [systemAdmin, loadOrganizations, loadAdmins]);

  const tenantMap = useMemo(() => {
    const map = {};
    (organizations || []).forEach((c) => {
      map[c.id] = c.name;
    });
    return map;
  }, [organizations]);

  const handleOpenDialog = () => {
    const defaultOrgId = organizations.length === 1 ? String(organizations[0].id) : '';
    setEditingUser(null);
    setForm({ ...BASE_FORM, tenantId: defaultOrgId });
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    if (saving) return;
    setDialogOpen(false);
    setEditingUser(null);
    setForm({ ...BASE_FORM });
  };

  const handleEditUser = (admin) => {
    setEditingUser(admin);
    setForm({
      username: admin.username || '',
      email: admin.email || '',
      password: '',
      tenantId: admin.tenant_id ? String(admin.tenant_id) : '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const trimmedUsername = form.username.trim();
    const trimmedEmail = form.email.trim();
    const trimmedPassword = form.password.trim();
    const trimmedTenant = form.tenantId.trim();

    if (!trimmedUsername || !trimmedEmail) {
      toast.error('Username and email are required.');
      return;
    }

    if (!trimmedTenant) {
      toast.error('Please select an organization for this administrator.');
      return;
    }

    const payload = {
      username: trimmedUsername,
      email: trimmedEmail,
      tenant_id: Number(trimmedTenant),
      user_type: 'TENANT_ADMIN',
    };

    if (!editingUser) {
      if (!trimmedPassword) {
        toast.error('Password is required for new administrators.');
        return;
      }
      payload.password = trimmedPassword;
    } else if (trimmedPassword) {
      payload.password = trimmedPassword;
    }

    setSaving(true);
    try {
      if (editingUser) {
        await api.put(`/users/${editingUser.id}`, payload);
        toast.success('Organization administrator updated successfully');
      } else {
        await api.post('/users', payload);
        toast.success('Organization administrator created successfully');
      }

      handleCloseDialog();
      await loadAdmins();
    } catch (error) {
      const message = parseErrorMessage(error, 'Failed to save administrator');
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteUser = async (admin) => {
    if (!admin) return;
    const confirmMessage = `Are you sure you want to delete ${admin.username || 'this organization administrator'}?`;
    if (!window.confirm(confirmMessage)) return;

    try {
      await api.delete(`/users/${admin.id}`);
      toast.success('Organization administrator deleted');
      await loadAdmins();
    } catch (error) {
      const message = parseErrorMessage(error, 'Failed to delete administrator');
      toast.error(message);
    }
  };

  if (!systemAdmin) {
    return null;
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto my-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Organization Administrator Management</h1>
          <p className="text-sm text-muted-foreground">
            Create and manage organization administrators across the platform.
          </p>
        </div>
        <Button onClick={handleOpenDialog} leftIcon={<Plus className="h-4 w-4" />}>
          Add Organization Admin
        </Button>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-semibold">Username</TableHead>
              <TableHead className="font-semibold">Email</TableHead>
              <TableHead className="font-semibold">Organization</TableHead>
              <TableHead className="font-semibold">Type</TableHead>
              <TableHead className="text-right font-semibold">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {admins.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center">
                  <span className="text-muted-foreground">No organization administrators found yet.</span>
                </TableCell>
              </TableRow>
            ) : (
              admins.map((admin) => (
                <TableRow key={admin.id}>
                  <TableCell>{admin.username}</TableCell>
                  <TableCell>{admin.email}</TableCell>
                  <TableCell>{tenantMap[admin.tenant_id] || '—'}</TableCell>
                  <TableCell>
                    <Badge>Organization Admin</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => handleEditUser(admin)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleDeleteUser(admin)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      <Modal
        isOpen={dialogOpen}
        onClose={handleCloseDialog}
        title={editingUser ? 'Edit Organization Admin' : 'Add Organization Admin'}
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="admin-form" disabled={saving}>
              {saving ? 'Saving…' : editingUser ? 'Save Changes' : 'Add Organization Admin'}
            </Button>
          </div>
        }
      >
        <form id="admin-form" onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={form.username}
              onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
              required
            />
          </div>
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
              required
            />
          </div>
          <div>
            <Label htmlFor="password">
              {editingUser ? 'Password (leave blank to keep current)' : 'Password'}
            </Label>
            <Input
              id="password"
              type="password"
              value={form.password}
              onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
              required={!editingUser}
            />
          </div>
          <div>
            <Label htmlFor="organization">Organization</Label>
            <Select
              value={form.tenantId}
              onValueChange={(value) => setForm((prev) => ({ ...prev, tenantId: value }))}
            >
              <SelectTrigger id="organization">
                <SelectValue placeholder="Select an organization" />
              </SelectTrigger>
              <SelectContent>
                {organizations.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {organizations.length === 0 && (
              <p className="text-sm text-muted-foreground mt-1">
                No organizations available. Create an organization before adding administrators.
              </p>
            )}
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default SystemAdminUserManagement;
