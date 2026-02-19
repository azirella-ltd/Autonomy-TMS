/**
 * Unit tests for templatesSlice
 * Tests template library management, filtering, and selection
 */

import configureStore from 'redux-mock-store';
import thunk from 'redux-thunk';
import templatesReducer, {
  fetchTemplates,
  fetchTemplateById,
  setFilters,
  clearFilters,
  TemplatesState,
  Template,
} from '../../../src/store/slices/templatesSlice';
import { apiClient } from '../../../src/services/api';

// Mock API client
jest.mock('../../../src/services/api');

const middlewares = [thunk];
const mockStore = configureStore(middlewares);

describe('templatesSlice', () => {
  let store: any;

  const mockTemplate: Template = {
    id: 1,
    name: 'Default TBG',
    description: 'Standard Beer Game configuration',
    category: 'standard',
    difficulty: 'beginner',
    num_nodes: 4,
    num_rounds: 10,
    is_featured: true,
    tags: ['classic', 'educational'],
    metadata: {
      author: 'System',
      version: '1.0',
    },
  };

  beforeEach(() => {
    store = mockStore({
      templates: {
        templates: [],
        filteredTemplates: [],
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      },
    });
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should return initial state', () => {
      expect(templatesReducer(undefined, { type: 'unknown' })).toEqual({
        templates: [],
        filteredTemplates: [],
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      });
    });
  });

  describe('synchronous actions', () => {
    it('should handle setFilters', () => {
      const state = templatesReducer(undefined, setFilters({ category: 'standard' }));

      expect(state.filters.category).toBe('standard');
      expect(state.filters.difficulty).toBeNull();
      expect(state.filters.search).toBe('');
    });

    it('should handle multiple filters', () => {
      const state = templatesReducer(
        undefined,
        setFilters({
          category: 'advanced',
          difficulty: 'expert',
          search: 'complex',
        })
      );

      expect(state.filters).toEqual({
        category: 'advanced',
        difficulty: 'expert',
        search: 'complex',
      });
    });

    it('should handle clearFilters', () => {
      const initialState: TemplatesState = {
        templates: [mockTemplate],
        filteredTemplates: [],
        loading: false,
        error: null,
        filters: {
          category: 'standard',
          difficulty: 'beginner',
          search: 'test',
        },
      };

      const state = templatesReducer(initialState, clearFilters());

      expect(state.filters).toEqual({
        category: null,
        difficulty: null,
        search: '',
      });
      expect(state.filteredTemplates).toEqual([mockTemplate]);
    });
  });

  describe('filtering logic', () => {
    const templates: Template[] = [
      {
        ...mockTemplate,
        id: 1,
        name: 'Basic TBG',
        category: 'standard',
        difficulty: 'beginner',
      },
      {
        ...mockTemplate,
        id: 2,
        name: 'Advanced TBG',
        category: 'advanced',
        difficulty: 'expert',
      },
      {
        ...mockTemplate,
        id: 3,
        name: 'Complex Supply Chain',
        category: 'advanced',
        difficulty: 'intermediate',
      },
    ];

    it('should filter by category', () => {
      const initialState: TemplatesState = {
        templates,
        filteredTemplates: templates,
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const state = templatesReducer(initialState, setFilters({ category: 'advanced' }));

      expect(state.filteredTemplates).toHaveLength(2);
      expect(state.filteredTemplates.every((t) => t.category === 'advanced')).toBe(true);
    });

    it('should filter by difficulty', () => {
      const initialState: TemplatesState = {
        templates,
        filteredTemplates: templates,
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const state = templatesReducer(initialState, setFilters({ difficulty: 'beginner' }));

      expect(state.filteredTemplates).toHaveLength(1);
      expect(state.filteredTemplates[0].difficulty).toBe('beginner');
    });

    it('should filter by search term', () => {
      const initialState: TemplatesState = {
        templates,
        filteredTemplates: templates,
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const state = templatesReducer(initialState, setFilters({ search: 'complex' }));

      expect(state.filteredTemplates).toHaveLength(1);
      expect(state.filteredTemplates[0].name).toBe('Complex Supply Chain');
    });

    it('should apply multiple filters', () => {
      const initialState: TemplatesState = {
        templates,
        filteredTemplates: templates,
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const state = templatesReducer(
        initialState,
        setFilters({
          category: 'advanced',
          difficulty: 'intermediate',
        })
      );

      expect(state.filteredTemplates).toHaveLength(1);
      expect(state.filteredTemplates[0].name).toBe('Complex Supply Chain');
    });

    it('should handle case-insensitive search', () => {
      const initialState: TemplatesState = {
        templates,
        filteredTemplates: templates,
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const state = templatesReducer(initialState, setFilters({ search: 'ADVANCED' }));

      expect(state.filteredTemplates).toHaveLength(1);
      expect(state.filteredTemplates[0].name).toBe('Advanced TBG');
    });

    it('should return empty array when no matches', () => {
      const initialState: TemplatesState = {
        templates,
        filteredTemplates: templates,
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const state = templatesReducer(initialState, setFilters({ search: 'nonexistent' }));

      expect(state.filteredTemplates).toHaveLength(0);
    });
  });

  describe('fetchTemplates async thunk', () => {
    it('should handle successful fetch', async () => {
      const mockResponse = {
        data: {
          templates: [mockTemplate],
        },
      };

      (apiClient.getTemplates as jest.Mock).mockResolvedValue(mockResponse);

      const result = await store.dispatch(fetchTemplates());

      expect(result.type).toBe('templates/fetchTemplates/fulfilled');
      expect(result.payload).toEqual([mockTemplate]);
    });

    it('should handle fetch failure', async () => {
      const mockError = new Error('Network error');
      (apiClient.getTemplates as jest.Mock).mockRejectedValue(mockError);

      const result = await store.dispatch(fetchTemplates());

      expect(result.type).toBe('templates/fetchTemplates/rejected');
      expect(result.error.message).toBe('Network error');
    });

    it('should set loading state during fetch', () => {
      const pendingState = templatesReducer(undefined, {
        type: fetchTemplates.pending.type,
        meta: { requestId: '123', arg: undefined },
      });

      expect(pendingState.loading).toBe(true);
      expect(pendingState.error).toBeNull();
    });

    it('should update state on successful fetch', () => {
      const payload = [mockTemplate];

      const fulfilledState = templatesReducer(undefined, {
        type: fetchTemplates.fulfilled.type,
        payload,
        meta: { requestId: '123', arg: undefined },
      });

      expect(fulfilledState.loading).toBe(false);
      expect(fulfilledState.templates).toEqual([mockTemplate]);
      expect(fulfilledState.filteredTemplates).toEqual([mockTemplate]);
      expect(fulfilledState.error).toBeNull();
    });

    it('should preserve filters after fetch', () => {
      const initialState: TemplatesState = {
        templates: [],
        filteredTemplates: [],
        loading: false,
        error: null,
        filters: {
          category: 'standard',
          difficulty: null,
          search: '',
        },
      };

      const templates = [
        { ...mockTemplate, id: 1, category: 'standard' },
        { ...mockTemplate, id: 2, category: 'advanced' },
      ];

      const fulfilledState = templatesReducer(initialState, {
        type: fetchTemplates.fulfilled.type,
        payload: templates,
        meta: { requestId: '123', arg: undefined },
      });

      expect(fulfilledState.filters.category).toBe('standard');
      expect(fulfilledState.filteredTemplates).toHaveLength(1);
      expect(fulfilledState.filteredTemplates[0].category).toBe('standard');
    });
  });

  describe('fetchTemplateById async thunk', () => {
    it('should handle successful fetch', async () => {
      const mockResponse = {
        data: mockTemplate,
      };

      (apiClient.getTemplateById as jest.Mock).mockResolvedValue(mockResponse);

      const result = await store.dispatch(fetchTemplateById(1));

      expect(result.type).toBe('templates/fetchTemplateById/fulfilled');
      expect(result.payload).toEqual(mockTemplate);
    });

    it('should add template if not in list', () => {
      const fulfilledState = templatesReducer(undefined, {
        type: fetchTemplateById.fulfilled.type,
        payload: mockTemplate,
        meta: { requestId: '123', arg: 1 },
      });

      expect(fulfilledState.templates).toHaveLength(1);
      expect(fulfilledState.templates[0]).toEqual(mockTemplate);
    });

    it('should update template if already in list', () => {
      const initialState: TemplatesState = {
        templates: [mockTemplate],
        filteredTemplates: [mockTemplate],
        loading: false,
        error: null,
        filters: {
          category: null,
          difficulty: null,
          search: '',
        },
      };

      const updatedTemplate = {
        ...mockTemplate,
        name: 'Updated TBG',
        description: 'Updated description',
      };

      const fulfilledState = templatesReducer(initialState, {
        type: fetchTemplateById.fulfilled.type,
        payload: updatedTemplate,
        meta: { requestId: '123', arg: 1 },
      });

      expect(fulfilledState.templates).toHaveLength(1);
      expect(fulfilledState.templates[0].name).toBe('Updated TBG');
    });
  });

  describe('edge cases', () => {
    it('should handle undefined error message', () => {
      const rejectedState = templatesReducer(undefined, {
        type: fetchTemplates.rejected.type,
        error: {},
        meta: { requestId: '123', arg: undefined },
      });

      expect(rejectedState.error).toBe('An error occurred');
    });

    it('should handle empty templates array', () => {
      const fulfilledState = templatesReducer(undefined, {
        type: fetchTemplates.fulfilled.type,
        payload: [],
        meta: { requestId: '123', arg: undefined },
      });

      expect(fulfilledState.templates).toEqual([]);
      expect(fulfilledState.filteredTemplates).toEqual([]);
    });

    it('should handle partial filter updates', () => {
      const initialState: TemplatesState = {
        templates: [mockTemplate],
        filteredTemplates: [mockTemplate],
        loading: false,
        error: null,
        filters: {
          category: 'standard',
          difficulty: 'beginner',
          search: 'test',
        },
      };

      const state = templatesReducer(initialState, setFilters({ category: 'advanced' }));

      expect(state.filters.category).toBe('advanced');
      expect(state.filters.difficulty).toBe('beginner');
      expect(state.filters.search).toBe('test');
    });

    it('should handle null/undefined values in setFilters', () => {
      const initialState: TemplatesState = {
        templates: [mockTemplate],
        filteredTemplates: [mockTemplate],
        loading: false,
        error: null,
        filters: {
          category: 'standard',
          difficulty: 'beginner',
          search: 'test',
        },
      };

      const state = templatesReducer(
        initialState,
        setFilters({
          category: null,
          difficulty: undefined,
        })
      );

      expect(state.filters.category).toBeNull();
      expect(state.filters.difficulty).toBeUndefined();
    });

    it('should reapply filters after template update', () => {
      const initialState: TemplatesState = {
        templates: [mockTemplate],
        filteredTemplates: [mockTemplate],
        loading: false,
        error: null,
        filters: {
          category: 'standard',
          difficulty: null,
          search: '',
        },
      };

      const updatedTemplate = {
        ...mockTemplate,
        category: 'advanced',
      };

      const fulfilledState = templatesReducer(initialState, {
        type: fetchTemplateById.fulfilled.type,
        payload: updatedTemplate,
        meta: { requestId: '123', arg: 1 },
      });

      // Should be filtered out since category changed to 'advanced'
      expect(fulfilledState.filteredTemplates).toHaveLength(0);
    });
  });
});
