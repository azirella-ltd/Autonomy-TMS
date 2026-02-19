import React, { useState, useEffect, useCallback } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  Checkbox,
  Input,
  Label,
  Modal,
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
} from '../components/common';
import { Plus, Trash2, Pencil, KeyRound } from 'lucide-react';
import { api } from '../services/api';
import { getUserType as resolveUserType } from '../utils/authUtils';
import { toast } from 'sonner';

const Users = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingUser, setEditingUser] = useState(null);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    is_admin: false
  });
  const [isOpen, setIsOpen] = useState(false);
  const cancelRef = React.useRef();

  const [isPwOpen, setPwOpen] = useState(false);
  const [pwUser, setPwUser] = useState(null);
  const [newPassword, setNewPassword] = useState('');

  const fetchUsers = useCallback(async () => {
    try {
      const response = await api.get('/users/');
      setUsers(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching users:', error);
      toast.error('Failed to fetch users');
      setLoading(false);
    }
  }, []);

  const toggleAdmin = async (user) => {
    try {
      const currentType = resolveUserType(user);
      const nextType = currentType === 'systemadmin' ? 'Player' : 'SystemAdmin';
      await api.put(`/users/${user.id}`, { user_type: nextType });
      toast.success('Role updated');
      fetchUsers();
    } catch (e) {
      toast.error('Failed to update role', {
        description: e?.response?.data?.detail || e.message,
      });
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData({
      ...formData,
      [name]: type === 'checkbox' ? checked : value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const targetType = formData.is_admin ? 'SystemAdmin' : 'Player';
      if (editingUser) {
        // Update: email/full_name only (password uses change-password endpoint)
        await api.put(`/users/${editingUser.id}`, {
          email: formData.email,
          full_name: formData.full_name || undefined,
          user_type: targetType,
        });
        toast.success('User updated');
      } else {
        await api.post('/users/', {
          username: formData.username,
          email: formData.email,
          password: formData.password || undefined,
          user_type: targetType,
        });
        toast.success('User created');
      }
      handleClose();
      fetchUsers();
    } catch (error) {
      console.error('Error saving user:', error);
      toast.error(error.response?.data?.detail || 'Failed to save user');
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setFormData({
      username: user.username,
      email: user.email,
      password: '',
      is_admin: resolveUserType(user) === 'systemadmin'
    });
    setIsOpen(true);
  };

  const handleDelete = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user?')) return;
    try {
      await api.delete(`/users/${userId}`);
      toast.info('User deleted');
      fetchUsers();
    } catch (error) {
      console.error('Error deleting user:', error);
      toast.error('Failed to delete user');
    }
  };

  const handleClose = () => {
    setEditingUser(null);
    setFormData({
      username: '',
      email: '',
      password: '',
      is_admin: false
    });
    setIsOpen(false);
  };

  const handlePasswordChange = async () => {
    try {
      await api.post(`/users/${pwUser.id}/change-password`, { current_password: '', new_password: newPassword });
      toast.success('Password updated');
      setPwOpen(false);
    } catch (e) {
      toast.error('Failed to update password', {
        description: e?.response?.data?.detail || e.message,
      });
    }
  };

  if (loading) {
    return <div className="p-4">Loading users...</div>;
  }

  return (
    <div className="p-4">
      <div className="space-y-4">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-2xl font-bold">User Management</h1>
          <Button onClick={() => setIsOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
            Add User
          </Button>
        </div>

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Username</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell>
                        <span className="truncate max-w-[12rem] sm:max-w-[16rem] md:max-w-[20rem] block">
                          {user.username}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="truncate max-w-[16rem] sm:max-w-[22rem] md:max-w-[28rem] block">
                          {user.email}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Badge variant={resolveUserType(user) === 'systemadmin' ? 'default' : 'success'}>
                            {resolveUserType(user) === 'systemadmin' ? 'Admin' : 'User'}
                          </Badge>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Checkbox
                                  checked={resolveUserType(user) === 'systemadmin'}
                                  onCheckedChange={() => toggleAdmin(user)}
                                />
                              </TooltipTrigger>
                              <TooltipContent>
                                {resolveUserType(user) === 'systemadmin' ? 'Revoke admin' : 'Make admin'}
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleEdit(user)}
                                >
                                  <Pencil className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Edit user</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => { setPwUser(user); setNewPassword(''); setPwOpen(true); }}
                                >
                                  <KeyRound className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Change password</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleDelete(user.id)}
                                  className="text-destructive hover:text-destructive"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Delete user</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Add/Edit User Modal */}
      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title={editingUser ? 'Edit User' : 'Add New User'}
      >
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                value={formData.username}
                onChange={handleInputChange}
                placeholder="Enter username"
                required
              />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                placeholder="Enter email"
                required
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                name="password"
                value={formData.password}
                onChange={handleInputChange}
                placeholder={editingUser ? 'Leave blank to keep current' : 'Enter password'}
                required={!editingUser}
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="is_admin"
                name="is_admin"
                checked={formData.is_admin}
                onCheckedChange={(checked) => setFormData({ ...formData, is_admin: checked })}
              />
              <Label htmlFor="is_admin">Admin User</Label>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <Button type="button" variant="ghost" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit">
              {editingUser ? 'Update' : 'Create'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Change Password Modal */}
      <Modal
        isOpen={isPwOpen}
        onClose={() => setPwOpen(false)}
        title="Change Password"
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="new-password">New Password</Label>
            <Input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="ghost" onClick={() => setPwOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handlePasswordChange}>
            Update
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default Users;
