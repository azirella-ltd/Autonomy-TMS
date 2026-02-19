/**
 * Templates Slice
 * Phase 7 Sprint 1: Mobile Application
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiClient } from '../../services/api';

interface Template {
  id: number;
  name: string;
  description: string;
  category: string;
  industry: string;
  difficulty: string;
  usage_count: number;
  is_featured: boolean;
  tags: string[];
}

interface TemplatesState {
  templates: Template[];
  featuredTemplates: Template[];
  currentTemplate: Template | null;
  loading: boolean;
  error: string | null;
  page: number;
  totalPages: number;
  filters: {
    query: string;
    category: string;
    industry: string;
    difficulty: string;
  };
}

const initialState: TemplatesState = {
  templates: [],
  featuredTemplates: [],
  currentTemplate: null,
  loading: false,
  error: null,
  page: 1,
  totalPages: 1,
  filters: {
    query: '',
    category: '',
    industry: '',
    difficulty: '',
  },
};

// Async thunks
export const fetchTemplates = createAsyncThunk(
  'templates/fetchTemplates',
  async (params: {
    page?: number;
    query?: string;
    category?: string;
    industry?: string;
    difficulty?: string;
  } = {}) => {
    const response = await apiClient.getTemplates({ ...params, page_size: 20 });
    return response.data;
  }
);

export const fetchFeaturedTemplates = createAsyncThunk(
  'templates/fetchFeatured',
  async () => {
    const response = await apiClient.getFeaturedTemplates(10);
    return response.data;
  }
);

export const fetchTemplate = createAsyncThunk(
  'templates/fetchTemplate',
  async (id: number) => {
    const response = await apiClient.getTemplate(id);
    return response.data;
  }
);

export const useTemplate = createAsyncThunk(
  'templates/useTemplate',
  async (id: number) => {
    const response = await apiClient.useTemplate(id);
    return response.data;
  }
);

// Slice
const templatesSlice = createSlice({
  name: 'templates',
  initialState,
  reducers: {
    setFilters: (state, action) => {
      state.filters = { ...state.filters, ...action.payload };
    },
    clearFilters: (state) => {
      state.filters = initialState.filters;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    // Fetch templates
    builder
      .addCase(fetchTemplates.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchTemplates.fulfilled, (state, action) => {
        state.loading = false;
        state.templates = action.payload.templates || action.payload;
        state.page = action.payload.page || 1;
        state.totalPages = action.payload.total_pages || 1;
      })
      .addCase(fetchTemplates.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch templates';
      });

    // Fetch featured
    builder
      .addCase(fetchFeaturedTemplates.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchFeaturedTemplates.fulfilled, (state, action) => {
        state.loading = false;
        state.featuredTemplates = action.payload;
      })
      .addCase(fetchFeaturedTemplates.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch featured templates';
      });

    // Fetch single template
    builder
      .addCase(fetchTemplate.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchTemplate.fulfilled, (state, action) => {
        state.loading = false;
        state.currentTemplate = action.payload;
      })
      .addCase(fetchTemplate.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch template';
      });

    // Use template
    builder
      .addCase(useTemplate.pending, (state) => {
        state.loading = true;
      })
      .addCase(useTemplate.fulfilled, (state) => {
        state.loading = false;
        if (state.currentTemplate) {
          state.currentTemplate.usage_count += 1;
        }
      })
      .addCase(useTemplate.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to use template';
      });
  },
});

export const { setFilters, clearFilters, clearError } = templatesSlice.actions;
export default templatesSlice.reducer;
