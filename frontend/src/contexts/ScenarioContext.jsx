import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { useWebSocket } from './WebSocketContext';
import simulationApi from '../services/api';

const ScenarioContext = createContext({
  // Scenario state
  scenario: null,
  currentScenarioUser: null,
  isScenarioOwner: false,
  isScenarioActive: false,
  isLoading: true,

  // Scenario actions
  submitOrder: async () => {},
  startScenario: async () => {},
  endScenario: async () => {},
  leaveScenario: async () => {},
  setScenarioUserReady: async () => {},
  sendChatMessage: async () => {},

  // UI state
  activeTab: 'scenario',
  setActiveTab: () => {},

  // Chat
  chatMessages: [],

  // Error handling
  error: null,
});

export const ScenarioProvider = ({ children }) => {
  const { scenarioId } = useParams();
  const { user } = useAuth();
  const { isConnected, sendMessage, subscribe, connect } = useWebSocket();

  // Scenario state
  const [scenario, setScenario] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('scenario');
  const [chatMessages, setChatMessages] = useState([]);

  // Derived state
  const currentScenarioUser = scenario?.scenarioUsers?.find(p => p.user_id === user?.id);
  const isScenarioOwner = scenario?.created_by === user?.id;
  const isScenarioActive = scenario?.status === 'in_progress';

  // Connect to WebSocket when scenario and scenarioUser are loaded
  useEffect(() => {
    if (scenarioId && currentScenarioUser?.id && isConnected === false) {
      // Connect to WebSocket with scenario ID and scenarioUser ID
      const connected = connect(scenarioId, currentScenarioUser.id);
      if (!connected) {
        console.error('Failed to connect to WebSocket');
      }
    }
  }, [scenarioId, currentScenarioUser?.id, isConnected, connect]);

  // Fetch scenario data
  const fetchScenario = useCallback(async () => {
    if (!scenarioId) return;

    try {
      setIsLoading(true);
      const scenarioData = await simulationApi.getScenario(scenarioId);
      setScenario(scenarioData);
      setError(null);

      // If we have chat messages, update the chat
      if (scenarioData.chat_messages) {
        setChatMessages(scenarioData.chat_messages);
      }
    } catch (err) {
      console.error('Failed to fetch scenario:', err);
      setError('Failed to load scenario. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [scenarioId]);

  // Connect to WebSocket when component mounts or scenario changes
  useEffect(() => {
    if (scenarioId) {
      // Connect to WebSocket for this scenario
      sendMessage('connect', { scenarioId });

      // Initial scenario data fetch
      fetchScenario();

      // Set up polling for scenario updates (fallback)
      const pollInterval = setInterval(fetchScenario, 30000); // Every 30 seconds

      return () => {
        clearInterval(pollInterval);
        // Don't disconnect WebSocket here as it might be used by other components
      };
    }
  }, [scenarioId, fetchScenario, sendMessage]);

  // Handle WebSocket messages
  useEffect(() => {
    if (!isConnected) return;

    const handleMessage = (event, data) => {
      switch (event) {
        case 'scenario_update':
          setScenario(prevScenario => ({
            ...prevScenario,
            ...data.scenario,
            // Preserve scenarioUsers array if not provided in update
            scenarioUsers: data.scenario.scenarioUsers || prevScenario?.scenarioUsers || []
          }));
          break;

        case 'chat_message':
          setChatMessages(prev => [...prev, data]);
          break;

        case 'participant_joined':
        case 'participant_left':
        case 'participant_ready':
          fetchScenario(); // Refresh scenario data
          break;

        case 'scenario_started':
          setScenario(prev => ({ ...prev, status: 'in_progress' }));
          break;

        case 'scenario_ended':
          setScenario(prev => ({ ...prev, status: 'completed' }));
          break;

        case 'error':
          console.error('Scenario error:', data);
          setError(data.message || 'An error occurred');
          break;

        default:
          console.warn('Unhandled WebSocket message:', event, data);
      }
    };

    // Subscribe to WebSocket events
    const unsubscribe = subscribe(handleMessage);
    return () => unsubscribe();
  }, [isConnected, fetchScenario, subscribe]);

  // Scenario actions
  const submitOrder = async (amount) => {
    if (!scenarioId || !amount) return false;

    try {
      await simulationApi.submitOrder(scenarioId, { amount: parseInt(amount, 10) });
      return true;
    } catch (error) {
      console.error('Failed to submit order:', error);
      setError(error.response?.data?.detail || 'Failed to submit order');
      return false;
    }
  };

  const startScenario = async () => {
    if (!scenarioId) return false;

    try {
      await simulationApi.startScenario(scenarioId);
      return true;
    } catch (error) {
      console.error('Failed to start scenario:', error);
      setError(error.response?.data?.detail || 'Failed to start scenario');
      return false;
    }
  };

  const endScenario = async () => {
    if (!scenarioId) return false;

    try {
      await simulationApi.endScenario(scenarioId);
      return true;
    } catch (error) {
      console.error('Failed to end scenario:', error);
      setError(error.response?.data?.detail || 'Failed to end scenario');
      return false;
    }
  };

  const leaveScenario = async () => {
    if (!scenarioId) return false;

    try {
      await simulationApi.leaveScenario(scenarioId);
      return true;
    } catch (error) {
      console.error('Failed to leave scenario:', error);
      setError(error.response?.data?.detail || 'Failed to leave scenario');
      return false;
    }
  };

  const setScenarioUserReady = async (isReady) => {
    if (!scenarioId) return false;

    try {
      await simulationApi.setScenarioUserReady(scenarioId, { is_ready: isReady });
      return true;
    } catch (error) {
      console.error('Failed to set scenarioUser ready status:', error);
      setError('Failed to update ready status');
      return false;
    }
  };

  const sendChatMessage = async (message) => {
    if (!scenarioId || !message?.trim()) return false;

    try {
      if (isConnected) {
        sendMessage('chat_message', {
          message: message.trim(),
          sender: user.username,
          timestamp: new Date().toISOString()
        });
      } else {
        // Fallback to HTTP if WebSocket is not available
        await simulationApi.sendChatMessage(scenarioId, message.trim());
      }
      return true;
    } catch (error) {
      console.error('Failed to send chat message:', error);
      return false;
    }
  };

  // Context value
  const value = {
    // Scenario state
    scenario,
    currentScenarioUser,
    isScenarioOwner,
    isScenarioActive,
    isLoading,

    // Scenario actions
    submitOrder,
    startScenario,
    endScenario,
    leaveScenario,
    setScenarioUserReady,
    sendChatMessage,

    // UI state
    activeTab,
    setActiveTab,

    // Chat
    chatMessages,

    // Error handling
    error,
  };

  return (
    <ScenarioContext.Provider value={value}>
      {children}
    </ScenarioContext.Provider>
  );
};

export const useScenario = () => {
  const context = useContext(ScenarioContext);
  if (context === undefined) {
    throw new Error('useScenario must be used within a ScenarioProvider');
  }
  return context;
};
