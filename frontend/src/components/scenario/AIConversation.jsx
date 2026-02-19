import { useState, useEffect, useRef } from "react";
import {
  PaperAirplaneIcon,
  TrashIcon,
  ArrowPathIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import { toast } from "react-toastify";
import simulationApi from "../../services/api";

/**
 * AIConversation Component
 * Phase 7 Sprint 4 - Multi-Turn Conversations
 *
 * Enables contextual, multi-turn conversations with AI assistant.
 * The AI remembers previous messages and provides follow-up responses.
 */
const AIConversation = ({ scenarioId, playerRole }) => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingHistory, setIsFetchingHistory] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch conversation history on mount
  useEffect(() => {
    fetchConversationHistory();
  }, [scenarioId]);

  const fetchConversationHistory = async () => {
    try {
      setIsFetchingHistory(true);
      const response = await simulationApi.getConversationHistory(scenarioId, 50);
      setMessages(response.messages || []);
    } catch (error) {
      console.error("Failed to fetch conversation history:", error);
      // Don't show error toast - empty history is fine
    } finally {
      setIsFetchingHistory(false);
    }
  };

  const sendMessage = async (messageText = null) => {
    const textToSend = messageText || inputMessage.trim();

    if (!textToSend) {
      toast.error("Please enter a message");
      return;
    }

    try {
      setIsLoading(true);

      // Optimistically add user message to UI
      const optimisticUserMsg = {
        id: Date.now(),
        role: "user",
        content: textToSend,
        created_at: new Date().toISOString(),
        context: {},
      };
      setMessages((prev) => [...prev, optimisticUserMsg]);
      setInputMessage("");

      // Send to API
      const response = await simulationApi.sendConversationMessage(scenarioId, {
        message: textToSend,
      });

      // Replace optimistic message with real messages
      setMessages((prev) => {
        const withoutOptimistic = prev.filter((m) => m.id !== optimisticUserMsg.id);
        return [
          ...withoutOptimistic,
          response.user_message,
          response.assistant_message,
        ];
      });

      // Focus back on input
      inputRef.current?.focus();
    } catch (error) {
      console.error("Failed to send message:", error);
      toast.error(
        error.response?.data?.detail || "Failed to send message. Please try again."
      );

      // Remove optimistic message on error
      setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMsg.id));

      // Restore input text
      setInputMessage(textToSend);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearConversation = async () => {
    if (!window.confirm("Clear all conversation history? This cannot be undone.")) {
      return;
    }

    try {
      await simulationApi.clearConversation(scenarioId);
      setMessages([]);
      toast.success("Conversation cleared");
    } catch (error) {
      console.error("Failed to clear conversation:", error);
      toast.error("Failed to clear conversation");
    }
  };

  const handleQuickReply = (question) => {
    setInputMessage(question);
    inputRef.current?.focus();
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const renderFollowUpQuestions = (message) => {
    const followUpQuestions = message.context?.follow_up_questions || [];

    if (followUpQuestions.length === 0) return null;

    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {followUpQuestions.map((question, idx) => (
          <button
            key={idx}
            onClick={() => handleQuickReply(question)}
            className="text-xs px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors"
          >
            {question}
          </button>
        ))}
      </div>
    );
  };

  const renderSuggestedAction = (message) => {
    const action = message.context?.suggested_action;

    if (!action) return null;

    return (
      <div className="mt-2 p-2 bg-green-50 border border-green-200 rounded">
        <p className="text-xs font-medium text-green-800">💡 Suggested Action:</p>
        <p className="text-sm text-green-700">
          {action.type === "order" && (
            <>Order <strong>{action.quantity}</strong> units</>
          )}
        </p>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg shadow">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gradient-to-r from-indigo-50 to-purple-50">
        <div className="flex items-center gap-2">
          <SparklesIcon className="h-5 w-5 text-indigo-600" />
          <h3 className="font-semibold text-gray-900">AI Conversation</h3>
          <span className="text-xs text-gray-500">
            ({playerRole})
          </span>
        </div>

        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={clearConversation}
              disabled={isLoading}
              className="text-sm text-gray-500 hover:text-red-600 transition-colors disabled:opacity-50"
              title="Clear conversation"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={fetchConversationHistory}
            disabled={isFetchingHistory}
            className="text-sm text-gray-500 hover:text-indigo-600 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isFetchingHistory ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
        {isFetchingHistory && messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <ArrowPathIcon className="h-8 w-8 text-gray-400 animate-spin mx-auto mb-2" />
              <p className="text-sm text-gray-500">Loading conversation...</p>
            </div>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-sm">
              <SparklesIcon className="h-12 w-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 mb-2">Start a conversation with your AI assistant</p>
              <p className="text-sm text-gray-400">
                Ask questions like "What should I order?" or "How's my inventory looking?"
              </p>
              <div className="mt-4 space-y-2">
                <button
                  onClick={() => sendMessage("What should I order?")}
                  className="block w-full text-sm px-4 py-2 bg-indigo-50 text-indigo-700 rounded hover:bg-indigo-100"
                >
                  💬 "What should I order?"
                </button>
                <button
                  onClick={() => sendMessage("How's my inventory?")}
                  className="block w-full text-sm px-4 py-2 bg-indigo-50 text-indigo-700 rounded hover:bg-indigo-100"
                >
                  📊 "How's my inventory?"
                </button>
              </div>
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <div
              key={message.id || index}
              className={`flex ${
                message.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[80%] ${
                  message.role === "user"
                    ? "bg-indigo-600 text-white rounded-lg rounded-br-none"
                    : "bg-gray-100 text-gray-900 rounded-lg rounded-bl-none"
                } px-4 py-2 shadow-sm`}
              >
                {/* Message Content */}
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>

                {/* Timestamp */}
                <p
                  className={`text-xs mt-1 ${
                    message.role === "user" ? "text-indigo-200" : "text-gray-500"
                  }`}
                >
                  {formatTime(message.created_at)}
                  {message.context?.confidence && (
                    <span className="ml-2">
                      • {Math.round(message.context.confidence * 100)}% confident
                    </span>
                  )}
                </p>

                {/* AI-specific features */}
                {message.role === "assistant" && (
                  <>
                    {renderSuggestedAction(message)}
                    {renderFollowUpQuestions(message)}
                  </>
                )}
              </div>
            </div>
          ))
        )}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg rounded-bl-none px-4 py-3 shadow-sm">
              <div className="flex items-center gap-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
                </div>
                <span className="text-xs text-gray-500">AI is thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 p-4 bg-gray-50">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask your AI assistant anything..."
            disabled={isLoading}
            rows={1}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none disabled:bg-gray-100 disabled:cursor-not-allowed"
            style={{ minHeight: "40px", maxHeight: "120px" }}
            onInput={(e) => {
              e.target.style.height = "40px";
              e.target.style.height = e.target.scrollHeight + "px";
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={isLoading || !inputMessage.trim()}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {isLoading ? (
              <ArrowPathIcon className="h-5 w-5 animate-spin" />
            ) : (
              <PaperAirplaneIcon className="h-5 w-5" />
            )}
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>

        <p className="text-xs text-gray-500 mt-2">
          💡 Tip: Ask follow-up questions for detailed advice. Press Enter to send.
        </p>
      </div>
    </div>
  );
};

export default AIConversation;
