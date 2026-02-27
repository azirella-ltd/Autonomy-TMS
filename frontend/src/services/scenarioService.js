import { api } from './api';

const SCENARIO_BASE_URL = '/games';

// Scenario CRUD operations
export const createScenario = async (scenarioData) => {
  const response = await api.post(SCENARIO_BASE_URL, scenarioData);
  return response.data;
};

export const getScenario = async (scenarioId) => {
  const response = await api.get(`${SCENARIO_BASE_URL}/${scenarioId}`);
  return response.data;
};

export const updateScenario = async (scenarioId, scenarioData) => {
  const response = await api.put(`${SCENARIO_BASE_URL}/${scenarioId}`, scenarioData);
  return response.data;
};

export const deleteScenario = async (scenarioId) => {
  await api.delete(`${SCENARIO_BASE_URL}/${scenarioId}`);
};

export const getScenarios = async (params = {}) => {
  const response = await api.get(SCENARIO_BASE_URL, { params });
  return response.data;
};

export const joinScenario = async (scenarioId, role) => {
  const response = await api.post(`${SCENARIO_BASE_URL}/${scenarioId}/join`, { role });
  return response.data;
};

export const startScenario = async (scenarioId) => {
  const response = await api.post(`${SCENARIO_BASE_URL}/${scenarioId}/start`);
  return response.data;
};

export const submitOrder = async (scenarioId, periodData) => {
  const response = await api.post(`${SCENARIO_BASE_URL}/${scenarioId}/order`, periodData);
  return response.data;
};

export const getScenarioState = async (scenarioId) => {
  const response = await api.get(`${SCENARIO_BASE_URL}/${scenarioId}/state`);
  return response.data;
};

export const getScenarioHistory = async (scenarioId) => {
  const response = await api.get(`${SCENARIO_BASE_URL}/${scenarioId}/history`);
  return response.data;
};

export const getScenarioConfig = async (scenarioId) => {
  const response = await api.get(`${SCENARIO_BASE_URL}/${scenarioId}/config`);
  return response.data;
};

export const updateScenarioConfig = async (scenarioId, config) => {
  const response = await api.put(`${SCENARIO_BASE_URL}/${scenarioId}/config`, config);
  return response.data;
};

// Export all functions as default for easier imports
const scenarioService = {
  createScenario,
  getScenario,
  updateScenario,
  deleteScenario,
  getScenarios,
  joinScenario,
  startScenario,
  submitOrder,
  getScenarioState,
  getScenarioHistory,
  getScenarioConfig,
  updateScenarioConfig,
};

export default scenarioService;
