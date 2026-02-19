/**
 * Chat Redux Slice
 * Manages A2A chat messages, agent suggestions, and real-time indicators
 * Phase 7 Sprint 2
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { apiClient } from '../../services/api';

// Types
export interface ChatMessage {
  id: string;
  gameId: number;
  senderId: string; // 'player:1' or 'agent:wholesaler'
  senderName: string;
  senderType: 'player' | 'agent';
  recipientId?: string; // null = broadcast
  content: string;
  type: 'text' | 'suggestion' | 'question' | 'analysis';
  metadata?: {
    suggestion?: {
      orderQuantity: number;
      confidence: number;
      rationale: string;
    };
    analysis?: {
      metric: string;
      value: number;
      trend: 'up' | 'down' | 'stable';
    };
  };
  timestamp: string;
  read: boolean;
  delivered: boolean;
}

export interface AgentSuggestion {
  id: string;
  gameId: number;
  round: number;
  agentName: string;
  orderQuantity: number;
  confidence: number; // 0-1
  rationale: string;
  context: {
    currentInventory: number;
    currentBacklog: number;
    recentDemand: number[];
    forecastDemand: number;
  };
  accepted?: boolean;
  timestamp: string;
}

export interface WhatIfAnalysis {
  question: string;
  answer: string;
  analysis: {
    scenario: any;
    outcome: any;
    recommendation: string;
  };
  timestamp: string;
}

export interface ChatState {
  messages: Record<number, ChatMessage[]>; // gameId -> messages
  unreadCounts: Record<number, number>; // gameId -> count
  typingIndicators: Record<string, boolean>; // agentId -> isTyping
  suggestions: Record<number, AgentSuggestion[]>; // gameId -> suggestions
  whatIfResults: WhatIfAnalysis[];
  loading: boolean;
  error: string | null;
}

const initialState: ChatState = {
  messages: {},
  unreadCounts: {},
  typingIndicators: {},
  suggestions: {},
  whatIfResults: [],
  loading: false,
  error: null,
};

// Async Thunks

export const fetchMessages = createAsyncThunk(
  'chat/fetchMessages',
  async ({ gameId, since }: { gameId: number; since?: string }) => {
    const params = since ? { since } : {};
    const response = await apiClient.get(`/api/v1/games/${gameId}/chat/messages`, {
      params,
    });
    return { gameId, messages: response.data.messages };
  }
);

export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (message: Omit<ChatMessage, 'id' | 'timestamp' | 'read' | 'delivered'>) => {
    const response = await apiClient.post(
      `/api/v1/games/${message.gameId}/chat/messages`,
      message
    );
    return response.data;
  }
);

export const markMessagesAsRead = createAsyncThunk(
  'chat/markMessagesAsRead',
  async ({ gameId, messageIds }: { gameId: number; messageIds: string[] }) => {
    await apiClient.put(`/api/v1/games/${gameId}/chat/messages/read`, {
      messageIds,
    });
    return { gameId, messageIds };
  }
);

export const requestSuggestion = createAsyncThunk(
  'chat/requestSuggestion',
  async ({ gameId, context }: { gameId: number; context?: any }) => {
    const response = await apiClient.post(
      `/api/v1/games/${gameId}/chat/request-suggestion`,
      { context }
    );
    return { gameId, suggestion: response.data };
  }
);

export const acceptSuggestion = createAsyncThunk(
  'chat/acceptSuggestion',
  async ({ gameId, suggestionId }: { gameId: number; suggestionId: string }) => {
    const response = await apiClient.put(
      `/api/v1/games/${gameId}/chat/suggestions/${suggestionId}/accept`
    );
    return { gameId, suggestionId, accepted: true };
  }
);

export const declineSuggestion = createAsyncThunk(
  'chat/declineSuggestion',
  async ({ gameId, suggestionId }: { gameId: number; suggestionId: string }) => {
    const response = await apiClient.put(
      `/api/v1/games/${gameId}/chat/suggestions/${suggestionId}/decline`
    );
    return { gameId, suggestionId, accepted: false };
  }
);

export const runWhatIfAnalysis = createAsyncThunk(
  'chat/runWhatIfAnalysis',
  async ({ gameId, question, scenario }: { gameId: number; question: string; scenario: any }) => {
    const response = await apiClient.post(`/api/v1/games/${gameId}/chat/what-if`, {
      question,
      scenario,
    });
    return response.data;
  }
);

// Slice
const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    addMessage: (state, action: PayloadAction<ChatMessage>) => {
      const { gameId } = action.payload;
      if (!state.messages[gameId]) {
        state.messages[gameId] = [];
      }
      state.messages[gameId].push(action.payload);

      // Update unread count if message is not from current user
      if (action.payload.senderType === 'agent' && !action.payload.read) {
        state.unreadCounts[gameId] = (state.unreadCounts[gameId] || 0) + 1;
      }
    },

    updateMessage: (state, action: PayloadAction<ChatMessage>) => {
      const { gameId, id } = action.payload;
      const messages = state.messages[gameId];
      if (messages) {
        const index = messages.findIndex((m) => m.id === id);
        if (index !== -1) {
          messages[index] = action.payload;
        }
      }
    },

    markMessageRead: (state, action: PayloadAction<{ gameId: number; messageId: string }>) => {
      const { gameId, messageId } = action.payload;
      const messages = state.messages[gameId];
      if (messages) {
        const message = messages.find((m) => m.id === messageId);
        if (message && !message.read) {
          message.read = true;
          state.unreadCounts[gameId] = Math.max(0, (state.unreadCounts[gameId] || 0) - 1);
        }
      }
    },

    markAllRead: (state, action: PayloadAction<number>) => {
      const gameId = action.payload;
      const messages = state.messages[gameId];
      if (messages) {
        messages.forEach((m) => {
          m.read = true;
        });
        state.unreadCounts[gameId] = 0;
      }
    },

    setTypingIndicator: (
      state,
      action: PayloadAction<{ agentId: string; isTyping: boolean }>
    ) => {
      const { agentId, isTyping } = action.payload;
      state.typingIndicators[agentId] = isTyping;
    },

    addSuggestion: (state, action: PayloadAction<AgentSuggestion>) => {
      const { gameId } = action.payload;
      if (!state.suggestions[gameId]) {
        state.suggestions[gameId] = [];
      }
      state.suggestions[gameId].push(action.payload);
    },

    updateSuggestion: (state, action: PayloadAction<AgentSuggestion>) => {
      const { gameId, id } = action.payload;
      const suggestions = state.suggestions[gameId];
      if (suggestions) {
        const index = suggestions.findIndex((s) => s.id === id);
        if (index !== -1) {
          suggestions[index] = action.payload;
        }
      }
    },

    clearChat: (state, action: PayloadAction<number>) => {
      const gameId = action.payload;
      delete state.messages[gameId];
      delete state.unreadCounts[gameId];
      delete state.suggestions[gameId];
    },

    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    // Fetch Messages
    builder.addCase(fetchMessages.pending, (state) => {
      state.loading = true;
      state.error = null;
    });
    builder.addCase(fetchMessages.fulfilled, (state, action) => {
      state.loading = false;
      const { gameId, messages } = action.payload;
      state.messages[gameId] = messages;

      // Calculate unread count
      const unreadCount = messages.filter((m) => !m.read && m.senderType === 'agent').length;
      state.unreadCounts[gameId] = unreadCount;
    });
    builder.addCase(fetchMessages.rejected, (state, action) => {
      state.loading = false;
      state.error = action.error.message || 'Failed to fetch messages';
    });

    // Send Message
    builder.addCase(sendMessage.pending, (state) => {
      state.loading = true;
      state.error = null;
    });
    builder.addCase(sendMessage.fulfilled, (state, action) => {
      state.loading = false;
      const message = action.payload;
      if (!state.messages[message.gameId]) {
        state.messages[message.gameId] = [];
      }
      // Check if message already exists (from WebSocket)
      const exists = state.messages[message.gameId].some((m) => m.id === message.id);
      if (!exists) {
        state.messages[message.gameId].push(message);
      }
    });
    builder.addCase(sendMessage.rejected, (state, action) => {
      state.loading = false;
      state.error = action.error.message || 'Failed to send message';
    });

    // Mark Messages as Read
    builder.addCase(markMessagesAsRead.fulfilled, (state, action) => {
      const { gameId, messageIds } = action.payload;
      const messages = state.messages[gameId];
      if (messages) {
        messageIds.forEach((id) => {
          const message = messages.find((m) => m.id === id);
          if (message) {
            message.read = true;
          }
        });
        // Recalculate unread count
        const unreadCount = messages.filter((m) => !m.read && m.senderType === 'agent').length;
        state.unreadCounts[gameId] = unreadCount;
      }
    });

    // Request Suggestion
    builder.addCase(requestSuggestion.pending, (state) => {
      state.loading = true;
      state.error = null;
    });
    builder.addCase(requestSuggestion.fulfilled, (state, action) => {
      state.loading = false;
      const { gameId, suggestion } = action.payload;
      if (!state.suggestions[gameId]) {
        state.suggestions[gameId] = [];
      }
      state.suggestions[gameId].push(suggestion);
    });
    builder.addCase(requestSuggestion.rejected, (state, action) => {
      state.loading = false;
      state.error = action.error.message || 'Failed to request suggestion';
    });

    // Accept Suggestion
    builder.addCase(acceptSuggestion.fulfilled, (state, action) => {
      const { gameId, suggestionId } = action.payload;
      const suggestions = state.suggestions[gameId];
      if (suggestions) {
        const suggestion = suggestions.find((s) => s.id === suggestionId);
        if (suggestion) {
          suggestion.accepted = true;
        }
      }
    });

    // Decline Suggestion
    builder.addCase(declineSuggestion.fulfilled, (state, action) => {
      const { gameId, suggestionId } = action.payload;
      const suggestions = state.suggestions[gameId];
      if (suggestions) {
        const suggestion = suggestions.find((s) => s.id === suggestionId);
        if (suggestion) {
          suggestion.accepted = false;
        }
      }
    });

    // What-If Analysis
    builder.addCase(runWhatIfAnalysis.pending, (state) => {
      state.loading = true;
      state.error = null;
    });
    builder.addCase(runWhatIfAnalysis.fulfilled, (state, action) => {
      state.loading = false;
      state.whatIfResults.push(action.payload);
    });
    builder.addCase(runWhatIfAnalysis.rejected, (state, action) => {
      state.loading = false;
      state.error = action.error.message || 'Failed to run what-if analysis';
    });
  },
});

export const {
  addMessage,
  updateMessage,
  markMessageRead,
  markAllRead,
  setTypingIndicator,
  addSuggestion,
  updateSuggestion,
  clearChat,
  clearError,
} = chatSlice.actions;

export default chatSlice.reducer;
