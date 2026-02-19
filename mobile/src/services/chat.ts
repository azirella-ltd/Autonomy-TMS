/**
 * Chat Service
 * Handles real-time chat with WebSocket integration
 * Phase 7 Sprint 2
 */

import { store } from '../store';
import {
  addMessage,
  updateMessage,
  setTypingIndicator,
  addSuggestion,
  ChatMessage,
  AgentSuggestion,
} from '../store/slices/chatSlice';
import { websocketService } from './websocket';

class ChatService {
  private initialized: boolean = false;

  /**
   * Initialize chat service with WebSocket handlers
   */
  initialize(): void {
    if (this.initialized) {
      return;
    }

    // Listen for new messages
    websocketService.on('chat:new_message', this.handleNewMessage);

    // Listen for agent typing indicators
    websocketService.on('chat:agent_typing', this.handleAgentTyping);

    // Listen for agent suggestions
    websocketService.on('chat:suggestion_ready', this.handleSuggestionReady);

    // Listen for message delivery confirmations
    websocketService.on('chat:message_delivered', this.handleMessageDelivered);

    // Listen for message read receipts
    websocketService.on('chat:message_read', this.handleMessageRead);

    this.initialized = true;
    console.log('Chat service initialized');
  }

  /**
   * Send a chat message
   */
  sendMessage(message: Omit<ChatMessage, 'id' | 'timestamp' | 'read' | 'delivered'>): void {
    websocketService.emit('chat:send_message', message);
  }

  /**
   * Send typing indicator
   */
  sendTypingIndicator(gameId: number, isTyping: boolean): void {
    websocketService.emit('chat:typing', { gameId, isTyping });
  }

  /**
   * Mark messages as read
   */
  markMessagesAsRead(gameId: number, messageIds: string[]): void {
    websocketService.emit('chat:mark_read', { gameId, messageIds });
  }

  /**
   * Request agent suggestion
   */
  requestSuggestion(gameId: number, context?: any): void {
    websocketService.emit('chat:request_suggestion', { gameId, context });
  }

  /**
   * Join chat room for a game
   */
  joinGameChat(gameId: number): void {
    websocketService.joinGame(gameId);
  }

  /**
   * Leave chat room for a game
   */
  leaveGameChat(gameId: number): void {
    websocketService.leaveGame(gameId);
  }

  /**
   * Handle new message received
   */
  private handleNewMessage = (data: ChatMessage): void => {
    console.log('New message received:', data);
    store.dispatch(addMessage(data));
  };

  /**
   * Handle agent typing indicator
   */
  private handleAgentTyping = (data: { agentId: string; isTyping: boolean }): void => {
    console.log('Agent typing:', data);
    store.dispatch(setTypingIndicator(data));
  };

  /**
   * Handle agent suggestion ready
   */
  private handleSuggestionReady = (data: AgentSuggestion): void => {
    console.log('Agent suggestion ready:', data);
    store.dispatch(addSuggestion(data));

    // Also create a chat message for the suggestion
    const message: ChatMessage = {
      id: `suggestion-${data.id}`,
      gameId: data.gameId,
      senderId: `agent:${data.agentName}`,
      senderName: data.agentName,
      senderType: 'agent',
      content: data.rationale,
      type: 'suggestion',
      metadata: {
        suggestion: {
          orderQuantity: data.orderQuantity,
          confidence: data.confidence,
          rationale: data.rationale,
        },
      },
      timestamp: data.timestamp,
      read: false,
      delivered: true,
    };
    store.dispatch(addMessage(message));
  };

  /**
   * Handle message delivered confirmation
   */
  private handleMessageDelivered = (data: { messageId: string; delivered: boolean }): void => {
    console.log('Message delivered:', data);
    // Update message delivery status
    // This would require fetching the full message from state and updating it
    // For simplicity, we'll handle this in the component
  };

  /**
   * Handle message read receipt
   */
  private handleMessageRead = (data: { messageId: string; read: boolean }): void => {
    console.log('Message read:', data);
    // Update message read status
    // This would require fetching the full message from state and updating it
  };

  /**
   * Format message for display
   */
  formatMessage(message: ChatMessage): string {
    switch (message.type) {
      case 'suggestion':
        return `💡 Suggestion: ${message.content}`;
      case 'question':
        return `❓ ${message.content}`;
      case 'analysis':
        return `📊 ${message.content}`;
      default:
        return message.content;
    }
  }

  /**
   * Get agent display name from agent ID
   */
  getAgentDisplayName(agentId: string): string {
    // Extract agent name from "agent:wholesaler" format
    if (agentId.startsWith('agent:')) {
      const name = agentId.replace('agent:', '');
      return name.charAt(0).toUpperCase() + name.slice(1);
    }
    return agentId;
  }

  /**
   * Get agent emoji based on role
   */
  getAgentEmoji(agentName: string): string {
    const emojiMap: Record<string, string> = {
      retailer: '🏪',
      wholesaler: '🏭',
      distributor: '🚛',
      factory: '🏗️',
      manufacturer: '⚙️',
    };
    return emojiMap[agentName.toLowerCase()] || '🤖';
  }

  /**
   * Get confidence color based on value
   */
  getConfidenceColor(confidence: number): string {
    if (confidence >= 0.8) return '#4caf50'; // High confidence - green
    if (confidence >= 0.6) return '#ff9800'; // Medium confidence - orange
    return '#f44336'; // Low confidence - red
  }

  /**
   * Format confidence percentage
   */
  formatConfidence(confidence: number): string {
    return `${Math.round(confidence * 100)}%`;
  }

  /**
   * Group messages by date
   */
  groupMessagesByDate(messages: ChatMessage[]): Record<string, ChatMessage[]> {
    const grouped: Record<string, ChatMessage[]> = {};

    messages.forEach((message) => {
      const date = new Date(message.timestamp).toLocaleDateString();
      if (!grouped[date]) {
        grouped[date] = [];
      }
      grouped[date].push(message);
    });

    return grouped;
  }

  /**
   * Get relative time string (e.g., "2 minutes ago")
   */
  getRelativeTime(timestamp: string): string {
    const now = new Date();
    const time = new Date(timestamp);
    const diffMs = now.getTime() - time.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return time.toLocaleDateString();
  }

  /**
   * Cleanup service
   */
  cleanup(): void {
    websocketService.off('chat:new_message', this.handleNewMessage);
    websocketService.off('chat:agent_typing', this.handleAgentTyping);
    websocketService.off('chat:suggestion_ready', this.handleSuggestionReady);
    websocketService.off('chat:message_delivered', this.handleMessageDelivered);
    websocketService.off('chat:message_read', this.handleMessageRead);
    this.initialized = false;
    console.log('Chat service cleaned up');
  }
}

export const chatService = new ChatService();
export default chatService;
