/**
 * User Editor Modal
 *
 * Modal dialog for creating/editing users with capability assignment.
 * Integrates CapabilitySelector for granular permission management.
 *
 * Migrated from Material-UI to Autonomy UI Kit.
 */

import React, { useState, useEffect } from 'react';
import {
  User,
  Shield,
  Save,
  X,
} from 'lucide-react';
import {
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  FormField,
  NativeSelect,
  SelectOption,
  Alert,
  Text,
} from '../common';
import { cn } from '../../lib/utils/cn';
import CapabilitySelector from './CapabilitySelector';

/**
 * UserEditor Component
 *
 * @param {Object} props
 * @param {boolean} props.open - Whether dialog is open
 * @param {Object} props.user - User object to edit (null for create)
 * @param {Function} props.onClose - Callback when dialog closes
 * @param {Function} props.onSave - Callback when user is saved
 */
const UserEditor = ({ open, user, onClose, onSave }) => {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    full_name: '',
    password: '',
    user_type: 'USER',
    is_active: true,
    capabilities: [],
  });

  // Initialize form when user prop changes
  useEffect(() => {
    if (user) {
      setFormData({
        email: user.email || '',
        username: user.username || '',
        full_name: user.full_name || '',
        password: '', // Never pre-fill password
        user_type: user.user_type || 'USER',
        is_active: user.is_active !== undefined ? user.is_active : true,
        capabilities: Array.isArray(user.capabilities) ? user.capabilities : [],
      });
    } else {
      // Reset for new user
      setFormData({
        email: '',
        username: '',
        full_name: '',
        password: '',
        user_type: 'USER',
        is_active: true,
        capabilities: [],
      });
    }
    setError(null);
  }, [user, open]);

  /**
   * Handle form field changes
   */
  const handleChange = (field) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  /**
   * Handle capability changes from CapabilitySelector
   */
  const handleCapabilitiesChange = (newCapabilities) => {
    setFormData(prev => ({
      ...prev,
      capabilities: newCapabilities,
    }));
  };

  /**
   * Validate form
   */
  const validateForm = () => {
    if (!formData.email || !formData.email.includes('@')) {
      setError('Valid email address is required');
      return false;
    }

    if (!user && !formData.password) {
      setError('Password is required for new users');
      return false;
    }

    if (formData.password && formData.password.length < 8) {
      setError('Password must be at least 8 characters');
      return false;
    }

    setError(null);
    return true;
  };

  /**
   * Handle save
   */
  const handleSave = async () => {
    if (!validateForm()) return;

    try {
      setSaving(true);
      setError(null);

      // Prepare data for API
      const userData = {
        email: formData.email,
        username: formData.username || null,
        full_name: formData.full_name || null,
        user_type: formData.user_type,
        is_active: formData.is_active,
        capabilities: formData.capabilities,
      };

      // Only include password if provided
      if (formData.password) {
        userData.password = formData.password;
      }

      await onSave(userData);
      // onSave callback will handle closing and success message
    } catch (err) {
      console.error('Error saving user:', err);
      setError(err.response?.data?.detail || 'Failed to save user');
    } finally {
      setSaving(false);
    }
  };

  /**
   * Handle close
   */
  const handleClose = () => {
    if (saving) return;
    onClose();
  };

  return (
    <Modal
      isOpen={open}
      onClose={handleClose}
      size="xl"
      className="min-h-[600px]"
    >
      <ModalHeader>
        <ModalTitle>
          {user ? `Edit User: ${user.email}` : 'Create New User'}
        </ModalTitle>
      </ModalHeader>

      <ModalBody className="py-4 max-h-[70vh] overflow-y-auto">
        {error && (
          <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <div className="flex flex-col gap-6">
          {/* Basic Info Section */}
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <User className="h-4 w-4" />
            <span>Basic Information</span>
          </div>

          <FormField
            label="Email Address"
            required
            helperText="Primary identifier for login"
          >
            <Input
              type="email"
              value={formData.email}
              onChange={handleChange('email')}
              disabled={saving}
              placeholder="user@example.com"
            />
          </FormField>

          <FormField
            label="Username"
            helperText="Optional username (if different from email)"
          >
            <Input
              value={formData.username}
              onChange={handleChange('username')}
              disabled={saving}
              placeholder="username"
            />
          </FormField>

          <FormField
            label="Full Name"
            helperText="Display name for the user"
          >
            <Input
              value={formData.full_name}
              onChange={handleChange('full_name')}
              disabled={saving}
              placeholder="John Doe"
            />
          </FormField>

          <FormField
            label="Password"
            required={!user}
            helperText={
              user
                ? 'Leave blank to keep existing password'
                : 'Required for new users (min 8 characters)'
            }
          >
            <Input
              type="password"
              value={formData.password}
              onChange={handleChange('password')}
              disabled={saving}
              placeholder="********"
            />
          </FormField>

          <hr className="border-border" />

          <FormField label="User Type" helperText="User has standard access, Customer Admin can manage users">
            <NativeSelect
              value={formData.user_type}
              onChange={handleChange('user_type')}
              disabled={saving}
            >
              <SelectOption value="USER">User</SelectOption>
              <SelectOption value="TENANT_ADMIN">Organization Admin</SelectOption>
            </NativeSelect>
          </FormField>

          <div className="flex items-center gap-3">
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={handleChange('is_active')}
                disabled={saving}
                className="sr-only peer"
              />
              <div className={cn(
                "w-11 h-6 bg-muted rounded-full peer peer-focus:ring-2 peer-focus:ring-ring peer-focus:ring-offset-2",
                "peer-checked:after:translate-x-full peer-checked:after:border-white",
                "after:content-[''] after:absolute after:top-0.5 after:left-[2px]",
                "after:bg-white after:border-gray-300 after:border after:rounded-full",
                "after:h-5 after:w-5 after:transition-all",
                "peer-checked:bg-primary",
                saving && "opacity-50 cursor-not-allowed"
              )} />
            </label>
            <span className="text-sm font-medium">Account Active</span>
          </div>

          {!formData.is_active && (
            <Alert variant="warning" className="mt-2">
              Inactive users cannot log in or access the system.
            </Alert>
          )}

          <hr className="border-border" />

          {/* Capabilities Section */}
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Shield className="h-4 w-4" />
            <span>User Capabilities</span>
          </div>

          <Text className="text-muted-foreground text-sm">
            Select the functional areas and permissions this user can access.
            Capabilities are organized hierarchically by area. View permissions
            grant read-only access, while Manage permissions allow creating and editing.
          </Text>

          <div className="border border-border rounded-lg p-4 max-h-[300px] overflow-y-auto">
            <CapabilitySelector
              selectedCapabilities={formData.capabilities}
              onChange={handleCapabilitiesChange}
              disabled={saving}
            />
          </div>
        </div>
      </ModalBody>

      <ModalFooter className="gap-2">
        <Button
          variant="outline"
          onClick={handleClose}
          disabled={saving}
          leftIcon={<X className="h-4 w-4" />}
        >
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          disabled={saving}
          loading={saving}
          leftIcon={!saving && <Save className="h-4 w-4" />}
        >
          {saving ? 'Saving...' : user ? 'Update User' : 'Create User'}
        </Button>
      </ModalFooter>
    </Modal>
  );
};

export default UserEditor;
