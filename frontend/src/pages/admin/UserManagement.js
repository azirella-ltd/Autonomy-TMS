import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Card,
  Spinner,
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
} from '../../components/common';
import { Plus, Trash2, Pencil, Shield } from 'lucide-react';
import { toast } from 'react-toastify';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { isSystemAdmin as isSystemAdminUser, getUserType as resolveUserType } from '../../utils/authUtils';
import UserEditor from '../../components/admin/UserEditor';

const parseErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object') {
    return detail.message || fallback;
  }
  return fallback;
};

function GroupPlayerManagement() {
  const navigate = useNavigate();
  const { isGroupAdmin, user } = useAuth();
  const systemAdmin = isSystemAdminUser(user);
  const rawGroupId = user?.group_id;
  const parsedGroupId = typeof rawGroupId === 'number' ? rawGroupId : Number(rawGroupId);
  const groupId = Number.isFinite(parsedGroupId) ? parsedGroupId : null;

  const [scenarioUsers, setPlayers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);

  useEffect(() => {
    if (!isGroupAdmin) {
      navigate('/unauthorized');
      return;
    }
    if (systemAdmin) {
      navigate('/system/users', { replace: true });
    }
  }, [isGroupAdmin, navigate, systemAdmin]);

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

  const loadPlayers = useCallback(async () => {
    if (!groupId) {
      setPlayers([]);
      return [];
    }

    try {
      const response = await api.get('/users', {
        params: { limit: 250, user_type: 'USER' },
      });
      const data = Array.isArray(response.data) ? response.data : [];
      const filtered = data.filter(
        (item) => resolveUserType(item) === 'user' && item.group_id === groupId,
      );
      setPlayers(filtered);
      return filtered;
    } catch (error) {
      console.error('Error loading scenarioUsers:', error);
      setPlayers([]);
      throw error;
    }
  }, [groupId]);

  useEffect(() => {
    if (!isGroupAdmin || systemAdmin) {
      setLoading(false);
      return;
    }

    if (!groupId) {
      setLoading(false);
      return;
    }

    const fetchAll = async () => {
      setLoading(true);
      try {
        await Promise.all([loadGroups(), loadPlayers()]);
      } catch (error) {
        toast.error('Failed to load user information');
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [groupId, isGroupAdmin, systemAdmin, loadGroups, loadPlayers]);

  const groupMap = useMemo(() => {
    const map = {};
    (groups || []).forEach((group) => {
      map[group.id] = group.name;
    });
    return map;
  }, [groups]);

  const handleCreateUser = () => {
    setSelectedUser(null);
    setEditorOpen(true);
  };

  const handleEditUser = (scenarioUser) => {
    setSelectedUser(scenarioUser);
    setEditorOpen(true);
  };

  const handleSaveUser = async (userData) => {
    if (!groupId) {
      toast.error('Your account is not linked to a group. Please contact your system administrator.');
      throw new Error('No group ID');
    }

    try {
      if (selectedUser) {
        await api.put(`/users/${selectedUser.id}`, userData);
        toast.success('User updated successfully');
      } else {
        await api.post('/users', {
          ...userData,
          group_id: groupId,
          user_type: userData.user_type || 'USER',
        });
        toast.success('User created successfully');
      }
      setEditorOpen(false);
      await loadPlayers();
    } catch (error) {
      const message = parseErrorMessage(error, 'Failed to save user');
      toast.error(message);
      throw error;
    }
  };

  const handleDeleteUser = async (scenarioUser) => {
    if (!scenarioUser) return;
    const confirmMessage = `Are you sure you want to delete ${user.username || 'this user'}?`;
    if (!window.confirm(confirmMessage)) return;

    try {
      await api.delete(`/users/${user.id}/`);
      toast.success('User deleted');
      await loadPlayers();
    } catch (error) {
      const message = parseErrorMessage(error, 'Failed to delete user');
      toast.error(message);
    }
  };

  if (!isGroupAdmin || systemAdmin) {
    return null;
  }

  if (!groupId) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Alert variant="warning">
          Your account is not linked to a group. Ask a system administrator to assign you before managing users.
        </Alert>
      </div>
    );
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
          <h1 className="text-2xl font-semibold">User Management</h1>
          <p className="text-sm text-muted-foreground">
            Manage users and assign capabilities within your group.
          </p>
        </div>
        <Button onClick={handleCreateUser} leftIcon={<Plus className="h-4 w-4" />}>
          Add User
        </Button>
      </div>

      <Alert variant="info" className="mb-6">
        <p className="text-sm">
          Click <strong>Edit</strong> to modify user details and assign capabilities.
          The editor has two tabs: <strong>Basic Info</strong> (name, email, password) and <strong>Capabilities</strong> (functional area permissions).
        </p>
      </Alert>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-semibold">Username</TableHead>
              <TableHead className="font-semibold">Email</TableHead>
              <TableHead className="font-semibold">Group</TableHead>
              <TableHead className="font-semibold">Type</TableHead>
              <TableHead className="font-semibold">Capabilities</TableHead>
              <TableHead className="text-right font-semibold">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center">
                  <span className="text-muted-foreground">No users found for your group yet.</span>
                </TableCell>
              </TableRow>
            ) : (
              users.map((scenarioUser) => {
                const type = resolveUserType(scenarioUser);
                const capCount = Array.isArray(user.capabilities) ? user.capabilities.length : 0;
                return (
                  <TableRow key={user.id}>
                    <TableCell>{user.username}</TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>{groupMap[user.group_id] || '—'}</TableCell>
                    <TableCell>
                      <Badge variant={type === 'user' ? 'success' : 'secondary'}>
                        {type === 'user' ? 'User' : type === 'groupadmin' ? 'Group Admin' : 'User'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge variant={capCount > 0 ? 'outline' : 'secondary'} className="gap-1">
                              <Shield className="h-3 w-3" />
                              {capCount} capabilities
                            </Badge>
                          </TooltipTrigger>
                          <TooltipContent>Number of capabilities assigned</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                    <TableCell className="text-right">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="sm" onClick={() => handleEditUser(scenarioUser)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Edit User & Capabilities</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleDeleteUser(scenarioUser)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete User</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </Card>

      <UserEditor
        open={editorOpen}
        user={selectedUser}
        onClose={() => setEditorOpen(false)}
        onSave={handleSaveUser}
      />
    </div>
  );
}

export default GroupPlayerManagement;
