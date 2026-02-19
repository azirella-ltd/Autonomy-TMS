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
  groupId: '',
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
  const [groups, setGroups] = useState([]);
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

  const loadGroups = useCallback(async () => {
    try {
      const response = await api.get('/groups');
      const data = Array.isArray(response.data) ? response.data : [];
      setGroups(data);
      return data;
    } catch (error) {
      console.error('Error loading groups:', error);
      setGroups([]);
      throw error;
    }
  }, []);

  const loadAdmins = useCallback(async () => {
    try {
      const response = await api.get('/users', { params: { user_type: 'GROUP_ADMIN', limit: 250 } });
      const data = Array.isArray(response.data) ? response.data : [];
      const filtered = data.filter((item) => resolveUserType(item) === 'groupadmin');
      setAdmins(filtered);
      return filtered;
    } catch (error) {
      console.error('Error loading group administrators:', error);
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
        await Promise.all([loadGroups(), loadAdmins()]);
      } catch (error) {
        toast.error('Failed to load user information');
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [systemAdmin, loadGroups, loadAdmins]);

  const groupMap = useMemo(() => {
    const map = {};
    (groups || []).forEach((group) => {
      map[group.id] = group.name;
    });
    return map;
  }, [groups]);

  const handleOpenDialog = () => {
    const defaultGroupId = groups.length === 1 ? String(groups[0].id) : '';
    setEditingUser(null);
    setForm({ ...BASE_FORM, groupId: defaultGroupId });
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
      groupId: admin.group_id ? String(admin.group_id) : '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const trimmedUsername = form.username.trim();
    const trimmedEmail = form.email.trim();
    const trimmedPassword = form.password.trim();
    const trimmedGroup = form.groupId.trim();

    if (!trimmedUsername || !trimmedEmail) {
      toast.error('Username and email are required.');
      return;
    }

    if (!trimmedGroup) {
      toast.error('Please select a group for this administrator.');
      return;
    }

    const payload = {
      username: trimmedUsername,
      email: trimmedEmail,
      group_id: Number(trimmedGroup),
      user_type: 'GROUP_ADMIN',
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
        toast.success('Group administrator updated successfully');
      } else {
        await api.post('/users', payload);
        toast.success('Group administrator created successfully');
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
    const confirmMessage = `Are you sure you want to delete ${admin.username || 'this group administrator'}?`;
    if (!window.confirm(confirmMessage)) return;

    try {
      await api.delete(`/users/${admin.id}`);
      toast.success('Group administrator deleted');
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
          <h1 className="text-2xl font-semibold">Group Administrator Management</h1>
          <p className="text-sm text-muted-foreground">
            Create and manage group administrators across the platform.
          </p>
        </div>
        <Button onClick={handleOpenDialog} leftIcon={<Plus className="h-4 w-4" />}>
          Add Group Admin
        </Button>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-semibold">Username</TableHead>
              <TableHead className="font-semibold">Email</TableHead>
              <TableHead className="font-semibold">Group</TableHead>
              <TableHead className="font-semibold">Type</TableHead>
              <TableHead className="text-right font-semibold">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {admins.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center">
                  <span className="text-muted-foreground">No group administrators found yet.</span>
                </TableCell>
              </TableRow>
            ) : (
              admins.map((admin) => (
                <TableRow key={admin.id}>
                  <TableCell>{admin.username}</TableCell>
                  <TableCell>{admin.email}</TableCell>
                  <TableCell>{groupMap[admin.group_id] || '—'}</TableCell>
                  <TableCell>
                    <Badge>Group Admin</Badge>
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
        title={editingUser ? 'Edit Group Admin' : 'Add Group Admin'}
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="admin-form" disabled={saving}>
              {saving ? 'Saving…' : editingUser ? 'Save Changes' : 'Add Group Admin'}
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
            <Label htmlFor="group">Group</Label>
            <Select
              value={form.groupId}
              onValueChange={(value) => setForm((prev) => ({ ...prev, groupId: value }))}
            >
              <SelectTrigger id="group">
                <SelectValue placeholder="Select a group" />
              </SelectTrigger>
              <SelectContent>
                {groups.map((group) => (
                  <SelectItem key={group.id} value={String(group.id)}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {groups.length === 0 && (
              <p className="text-sm text-muted-foreground mt-1">
                No groups available. Create a group before adding administrators.
              </p>
            )}
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default SystemAdminUserManagement;
