/**
 * RL (Reinforcement Learning) API Client
 *
 * Provides methods for interacting with the RL management API.
 */

import { api } from './api';

/**
 * Start RL training
 * @param {Object} config - Training configuration
 * @returns {Promise} Training status
 */
export const startTraining = async (config) => {
  const response = await api.post('/rl/train', config);
  return response.data;
};

/**
 * Get RL training status
 * @returns {Promise} Current training status
 */
export const getTrainingStatus = async () => {
  const response = await api.get('/rl/training-status');
  return response.data;
};

/**
 * Load an RL model
 * @param {string} modelPath - Path to model checkpoint
 * @param {string} device - Device (cpu or cuda)
 * @returns {Promise} Model info
 */
export const loadModel = async (modelPath, device = 'cpu') => {
  const response = await api.post('/rl/load-model', {
    model_path: modelPath,
    device: device
  });
  return response.data;
};

/**
 * Get RL model information
 * @returns {Promise} Model info
 */
export const getModelInfo = async () => {
  const response = await api.get('/rl/model-info');
  return response.data;
};

/**
 * List available RL checkpoints
 * @param {string} checkpointDir - Checkpoint directory
 * @param {string} algorithm - Optional algorithm filter (PPO, SAC, A2C)
 * @returns {Promise} List of checkpoints
 */
export const listCheckpoints = async (checkpointDir = './checkpoints/rl', algorithm = null) => {
  const params = { checkpoint_dir: checkpointDir };
  if (algorithm) {
    params.algorithm = algorithm;
  }
  const response = await api.get('/rl/checkpoints', { params });
  return response.data;
};

/**
 * Test RL model with sample input
 * @param {Object} testData - Test input data
 * @returns {Promise} Test results
 */
export const testModel = async (testData) => {
  const response = await api.post('/rl/test', testData);
  return response.data;
};

/**
 * Evaluate RL model
 * @param {string} modelPath - Path to model checkpoint
 * @param {number} nEpisodes - Number of evaluation episodes
 * @param {string} device - Device (cpu or cuda)
 * @returns {Promise} Evaluation results
 */
export const evaluateModel = async (modelPath, nEpisodes = 20, device = 'cpu') => {
  const response = await api.post('/rl/evaluate', {
    model_path: modelPath,
    n_episodes: nEpisodes,
    device: device
  });
  return response.data;
};

/**
 * Delete an RL checkpoint
 * @param {string} checkpointPath - Path to checkpoint
 * @returns {Promise} Success message
 */
export const deleteCheckpoint = async (checkpointPath) => {
  const response = await api.delete('/rl/checkpoint', {
    params: { checkpoint_path: checkpointPath }
  });
  return response.data;
};

/**
 * Stop ongoing training
 * @returns {Promise} Success message
 */
export const stopTraining = async () => {
  const response = await api.post('/rl/stop-training');
  return response.data;
};

export default {
  startTraining,
  getTrainingStatus,
  loadModel,
  getModelInfo,
  listCheckpoints,
  testModel,
  evaluateModel,
  deleteCheckpoint,
  stopTraining
};
