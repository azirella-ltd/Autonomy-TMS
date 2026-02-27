/**
 * Tenant Admin User Management
 *
 * Allows Organization Admins to manage users within their own organization and assign
 * granular functional area capabilities based on UI_UX_REQUIREMENTS.md
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../../components/common';
import {
  Plus,
  Pencil,
  Trash2,
  Search,
  MoreVertical,
  User,
  Shield,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { toast } from 'react-toastify';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useCapabilities } from '../../hooks/useCapabilities';
import UserEditor from '../../components/admin/UserEditor';

const TenantAdminUserManagement = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { hasCapability, loading: capLoading } = useCapabilities();

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);

  // Access allowed if user has manage_tenant_users capability or is admin
  const isSystemAdmin = user?.user_type === 'SYSTEM_ADMIN';
  const isTenantAdmin = user?.user_type === 'TENANT_ADMIN';
  const canViewUsers = hasCapability('view_users') || hasCapability('manage_tenant_users');
  const canEditUsers = hasCapability('manage_tenant_users') || isTenantAdmin || isSystemAdmin;

  useEffect(() => {
    if (!capLoading && user && !isSystemAdmin && !isTenantAdmin && !canViewUsers) {
      toast.error('Access denied. User management privileges required.');
      navigate('/unauthorized');
    }
  }, [user, navigate, isSystemAdmin, isTenantAdmin, canViewUsers, capLoading]);

  const loadUsers = useCallback(async () => {
    if (!user?.tenant_id) return;

    try {
      setLoading(true);
      const response = await api.get(`/tenants/${user.tenant_id}/users`);
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Error loading users:', error);
      toast.error('Failed to load users');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [user?.tenant_id]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const filteredUsers = users.filter((u) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      u.email?.toLowerCase().includes(query) ||
      u.username?.toLowerCase().includes(query) ||
      u.full_name?.toLowerCase().includes(query)
    );
  });

  const handleCreateUser = () => {
    setSelectedUser(null);
    setEditorOpen(true);
  };

  const handleEditUser = (userToEdit) => {
    setSelectedUser(userToEdit);
    setEditorOpen(true);
  };

  const handleSaveUser = async (userData) => {
    try {
      if (selectedUser) {
        await api.put(`/users/${selectedUser.id}`, userData);
        toast.success('User updated successfully');
      } else {
        await api.post('/users', {
          ...userData,
          tenant_id: user.tenant_id,
          user_type: 'USER',
        });
        toast.success('User created successfully');
      }
      setEditorOpen(false);
      loadUsers();
    } catch (error) {
      console.error('Error saving user:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to save user';
      toast.error(errorMsg);
      throw error;
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }

    try {
      await api.delete(`/users/${userId}`);
      toast.success('User deleted successfully');
      loadUsers();
    } catch (error) {
      console.error('Error deleting user:', error);
      toast.error('Failed to delete user');
    }
  };

  const handleToggleActive = async (userId, currentStatus) => {
    try {
      await api.patch(`/users/${userId}/status`, {
        is_active: !currentStatus,
      });
      toast.success(`User ${!currentStatus ? 'activated' : 'deactivated'} successfully`);
      loadUsers();
    } catch (error) {
      console.error('Error toggling user status:', error);
      toast.error('Failed to update user status');
    }
  };

  const getCapabilityCount = (u) => {
    if (!u.capabilities) return 0;
    if (Array.isArray(u.capabilities)) return u.capabilities.length;
    return 0;
  };

  const getUserTypeVariant = (userType) => {
    switch (userType) {
      case 'SYSTEM_ADMIN':
        return 'destructive';
      case 'TENANT_ADMIN':
        return 'warning';
      case 'USER':
      default:
        return 'secondary';
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="flex justify-center items-center min-h-[400px]">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">User Management</h1>
          <p className="text-sm text-muted-foreground">
            Manage users and assign functional area capabilities
          </p>
        </div>
        <Button onClick={handleCreateUser} leftIcon={<Plus className="h-4 w-4" />}>
          Create User
        </Button>
      </div>

      {/* Info Alert */}
      <Alert variant="info" className="mb-6">
        <p className="text-sm">
          As an Organization Admin, you can create and manage users within your organization.
          Assign granular capabilities to control access to specific functional areas
          (Planning, Execution, AI & Agents, Analytics, etc.).
        </p>
      </Alert>

      {/* Search Bar */}
      <Card className="mb-6">
        <CardContent className="py-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search users by name, email, or username..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>User Type</TableHead>
              <TableHead>Capabilities</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredUsers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8">
                  <p className="text-muted-foreground">
                    {searchQuery ? 'No users match your search' : 'No users found'}
                  </p>
                </TableCell>
              </TableRow>
            ) : (
              filteredUsers.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="font-semibold text-sm">
                          {u.full_name || u.username || 'Unnamed User'}
                        </p>
                        {u.username && u.full_name && (
                          <p className="text-xs text-muted-foreground">@{u.username}</p>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <p className="text-sm">{u.email}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant={getUserTypeVariant(u.user_type)}>
                      {u.user_type || 'USER'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge variant="outline" className="gap-1">
                            <Shield className="h-3 w-3" />
                            {getCapabilityCount(u)} capabilities
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          Number of functional area capabilities assigned
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </TableCell>
                  <TableCell>
                    {u.is_active ? (
                      <Badge variant="success" className="gap-1">
                        <CheckCircle className="h-3 w-3" />
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="gap-1">
                        <XCircle className="h-3 w-3" />
                        Inactive
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="sm" onClick={() => handleEditUser(u)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Edit user</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleEditUser(u)}>
                          <Pencil className="h-4 w-4 mr-2" />
                          Edit User
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleToggleActive(u.id, u.is_active)}>
                          {u.is_active ? (
                            <>
                              <XCircle className="h-4 w-4 mr-2" />
                              Deactivate
                            </>
                          ) : (
                            <>
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Activate
                            </>
                          )}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => handleDeleteUser(u.id)}
                          className="text-destructive"
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Delete User
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      {/* User Editor Dialog */}
      <UserEditor
        open={editorOpen}
        user={selectedUser}
        onClose={() => setEditorOpen(false)}
        onSave={handleSaveUser}
      />
    </div>
  );
};

export default TenantAdminUserManagement;
