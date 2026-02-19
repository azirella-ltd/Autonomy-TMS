/**
 * Register Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import {
  TextInput,
  Button,
  Text,
  HelperText,
  Checkbox,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import { register, clearError } from '../../store/slices/authSlice';
import { theme } from '../../theme';

export default function RegisterScreen({ navigation }: any) {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    firstName: '',
    lastName: '',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [errors, setErrors] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    firstName: '',
    lastName: '',
  });

  const dispatch = useAppDispatch();
  const { loading, error } = useAppSelector((state) => state.auth);

  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const validatePassword = (password: string): boolean => {
    // At least 8 characters, 1 uppercase, 1 lowercase, 1 number
    const passwordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;
    return passwordRegex.test(password);
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData({ ...formData, [field]: value });
    setErrors({ ...errors, [field]: '' });
  };

  const validateForm = (): boolean => {
    const newErrors = {
      email: '',
      password: '',
      confirmPassword: '',
      firstName: '',
      lastName: '',
    };

    let isValid = true;

    // Email validation
    if (!formData.email) {
      newErrors.email = 'Email is required';
      isValid = false;
    } else if (!validateEmail(formData.email)) {
      newErrors.email = 'Please enter a valid email';
      isValid = false;
    }

    // Password validation
    if (!formData.password) {
      newErrors.password = 'Password is required';
      isValid = false;
    } else if (!validatePassword(formData.password)) {
      newErrors.password =
        'Password must be at least 8 characters with uppercase, lowercase, and number';
      isValid = false;
    }

    // Confirm password validation
    if (!formData.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
      isValid = false;
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
      isValid = false;
    }

    // Name validation
    if (!formData.firstName) {
      newErrors.firstName = 'First name is required';
      isValid = false;
    }

    if (!formData.lastName) {
      newErrors.lastName = 'Last name is required';
      isValid = false;
    }

    setErrors(newErrors);
    return isValid;
  };

  const handleRegister = () => {
    dispatch(clearError());

    if (!validateForm()) {
      return;
    }

    if (!agreedToTerms) {
      return;
    }

    // Dispatch register action
    dispatch(
      register({
        email: formData.email,
        password: formData.password,
        first_name: formData.firstName,
        last_name: formData.lastName,
      })
    );
  };

  const handleBackToLogin = () => {
    navigation.goBack();
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Create Account</Text>
          <Text style={styles.subtitle}>Join The Beer Game platform</Text>
        </View>

        {/* Registration Form */}
        <View style={styles.form}>
          <TextInput
            label="First Name"
            value={formData.firstName}
            onChangeText={(text) => handleInputChange('firstName', text)}
            mode="outlined"
            autoCapitalize="words"
            textContentType="givenName"
            error={!!errors.firstName}
            disabled={loading}
            style={styles.input}
          />
          {errors.firstName ? (
            <HelperText type="error" visible={!!errors.firstName}>
              {errors.firstName}
            </HelperText>
          ) : null}

          <TextInput
            label="Last Name"
            value={formData.lastName}
            onChangeText={(text) => handleInputChange('lastName', text)}
            mode="outlined"
            autoCapitalize="words"
            textContentType="familyName"
            error={!!errors.lastName}
            disabled={loading}
            style={styles.input}
          />
          {errors.lastName ? (
            <HelperText type="error" visible={!!errors.lastName}>
              {errors.lastName}
            </HelperText>
          ) : null}

          <TextInput
            label="Email"
            value={formData.email}
            onChangeText={(text) => handleInputChange('email', text)}
            mode="outlined"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            textContentType="emailAddress"
            error={!!errors.email}
            disabled={loading}
            style={styles.input}
          />
          {errors.email ? (
            <HelperText type="error" visible={!!errors.email}>
              {errors.email}
            </HelperText>
          ) : null}

          <TextInput
            label="Password"
            value={formData.password}
            onChangeText={(text) => handleInputChange('password', text)}
            mode="outlined"
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            textContentType="newPassword"
            error={!!errors.password}
            disabled={loading}
            style={styles.input}
            right={
              <TextInput.Icon
                icon={showPassword ? 'eye-off' : 'eye'}
                onPress={() => setShowPassword(!showPassword)}
              />
            }
          />
          {errors.password ? (
            <HelperText type="error" visible={!!errors.password}>
              {errors.password}
            </HelperText>
          ) : null}

          <TextInput
            label="Confirm Password"
            value={formData.confirmPassword}
            onChangeText={(text) => handleInputChange('confirmPassword', text)}
            mode="outlined"
            secureTextEntry={!showConfirmPassword}
            autoCapitalize="none"
            textContentType="newPassword"
            error={!!errors.confirmPassword}
            disabled={loading}
            style={styles.input}
            right={
              <TextInput.Icon
                icon={showConfirmPassword ? 'eye-off' : 'eye'}
                onPress={() => setShowConfirmPassword(!showConfirmPassword)}
              />
            }
          />
          {errors.confirmPassword ? (
            <HelperText type="error" visible={!!errors.confirmPassword}>
              {errors.confirmPassword}
            </HelperText>
          ) : null}

          {/* Terms and Conditions */}
          <View style={styles.checkboxContainer}>
            <Checkbox
              status={agreedToTerms ? 'checked' : 'unchecked'}
              onPress={() => setAgreedToTerms(!agreedToTerms)}
              disabled={loading}
            />
            <Text style={styles.checkboxLabel}>
              I agree to the Terms of Service and Privacy Policy
            </Text>
          </View>

          {error ? (
            <HelperText type="error" visible={!!error} style={styles.errorText}>
              {error}
            </HelperText>
          ) : null}

          <Button
            mode="contained"
            onPress={handleRegister}
            loading={loading}
            disabled={loading || !agreedToTerms}
            style={styles.registerButton}
            contentStyle={styles.buttonContent}
          >
            {loading ? 'Creating Account...' : 'Create Account'}
          </Button>

          {/* Back to Login */}
          <Button
            mode="text"
            onPress={handleBackToLogin}
            disabled={loading}
            style={styles.backButton}
          >
            Already have an account? Sign In
          </Button>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: theme.spacing.lg,
  },
  header: {
    alignItems: 'center',
    marginBottom: theme.spacing.xl,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: theme.colors.primary,
    marginBottom: theme.spacing.xs,
  },
  subtitle: {
    fontSize: 16,
    color: theme.colors.textSecondary,
  },
  form: {
    width: '100%',
  },
  input: {
    marginBottom: theme.spacing.sm,
  },
  checkboxContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: theme.spacing.md,
  },
  checkboxLabel: {
    flex: 1,
    marginLeft: theme.spacing.sm,
    fontSize: 14,
    color: theme.colors.text,
  },
  errorText: {
    marginBottom: theme.spacing.sm,
  },
  registerButton: {
    marginTop: theme.spacing.md,
  },
  buttonContent: {
    paddingVertical: theme.spacing.sm,
  },
  backButton: {
    marginTop: theme.spacing.lg,
  },
});
