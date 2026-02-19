import { api } from './api';

const GAME_BASE_URL = '/games';

// Game CRUD operations
export const createGame = async (gameData) => {
  const response = await api.post(GAME_BASE_URL, gameData);
  return response.data;
};

export const getGame = async (gameId) => {
  const response = await api.get(`${GAME_BASE_URL}/${gameId}`);
  return response.data;
};

export const updateGame = async (gameId, gameData) => {
  const response = await api.put(`${GAME_BASE_URL}/${gameId}`, gameData);
  return response.data;
};

export const deleteGame = async (gameId) => {
  await api.delete(`${GAME_BASE_URL}/${gameId}`);
};

export const getGames = async (params = {}) => {
  const response = await api.get(GAME_BASE_URL, { params });
  return response.data;
};

export const joinGame = async (gameId, role) => {
  const response = await api.post(`${GAME_BASE_URL}/${gameId}/join`, { role });
  return response.data;
};

export const startGame = async (gameId) => {
  const response = await api.post(`${GAME_BASE_URL}/${gameId}/start`);
  return response.data;
};

export const submitOrder = async (gameId, roundData) => {
  const response = await api.post(`${GAME_BASE_URL}/${gameId}/order`, roundData);
  return response.data;
};

export const getGameState = async (gameId) => {
  const response = await api.get(`${GAME_BASE_URL}/${gameId}/state`);
  return response.data;
};

export const getGameHistory = async (gameId) => {
  const response = await api.get(`${GAME_BASE_URL}/${gameId}/history`);
  return response.data;
};

export const getGameConfig = async (gameId) => {
  const response = await api.get(`${GAME_BASE_URL}/${gameId}/config`);
  return response.data;
};

export const updateGameConfig = async (gameId, config) => {
  const response = await api.put(`${GAME_BASE_URL}/${gameId}/config`, config);
  return response.data;
};

// Export all functions as default for easier imports
const gameService = {
  createGame,
  getGame,
  updateGame,
  deleteGame,
  getGames,
  joinGame,
  startGame,
  submitOrder,
  getGameState,
  getGameHistory,
  getGameConfig,
  updateGameConfig,
};

export default gameService;
