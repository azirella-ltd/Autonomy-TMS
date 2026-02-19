/**
 * UI Slice
 * Phase 7 Sprint 1: Mobile Application
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
  duration?: number;
}

interface Modal {
  id: string;
  type: string;
  title?: string;
  content?: any;
  onConfirm?: () => void;
  onCancel?: () => void;
}

interface UIState {
  globalLoading: boolean;
  toasts: Toast[];
  modals: Modal[];
  bottomSheet: {
    visible: boolean;
    content: any;
  };
  theme: 'light' | 'dark';
  networkStatus: 'online' | 'offline';
}

const initialState: UIState = {
  globalLoading: false,
  toasts: [],
  modals: [],
  bottomSheet: {
    visible: false,
    content: null,
  },
  theme: 'light',
  networkStatus: 'online',
};

// Slice
const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setGlobalLoading: (state, action: PayloadAction<boolean>) => {
      state.globalLoading = action.payload;
    },

    showToast: (state, action: PayloadAction<Omit<Toast, 'id'>>) => {
      const id = Date.now().toString();
      state.toasts.push({
        id,
        ...action.payload,
        duration: action.payload.duration || 3000,
      });
    },

    hideToast: (state, action: PayloadAction<string>) => {
      state.toasts = state.toasts.filter((toast) => toast.id !== action.payload);
    },

    clearToasts: (state) => {
      state.toasts = [];
    },

    showModal: (state, action: PayloadAction<Omit<Modal, 'id'>>) => {
      const id = Date.now().toString();
      state.modals.push({
        id,
        ...action.payload,
      });
    },

    hideModal: (state, action: PayloadAction<string>) => {
      state.modals = state.modals.filter((modal) => modal.id !== action.payload);
    },

    clearModals: (state) => {
      state.modals = [];
    },

    showBottomSheet: (state, action: PayloadAction<any>) => {
      state.bottomSheet = {
        visible: true,
        content: action.payload,
      };
    },

    hideBottomSheet: (state) => {
      state.bottomSheet = {
        visible: false,
        content: null,
      };
    },

    setTheme: (state, action: PayloadAction<'light' | 'dark'>) => {
      state.theme = action.payload;
    },

    toggleTheme: (state) => {
      state.theme = state.theme === 'light' ? 'dark' : 'light';
    },

    setNetworkStatus: (state, action: PayloadAction<'online' | 'offline'>) => {
      state.networkStatus = action.payload;
    },
  },
});

export const {
  setGlobalLoading,
  showToast,
  hideToast,
  clearToasts,
  showModal,
  hideModal,
  clearModals,
  showBottomSheet,
  hideBottomSheet,
  setTheme,
  toggleTheme,
  setNetworkStatus,
} = uiSlice.actions;

export default uiSlice.reducer;
