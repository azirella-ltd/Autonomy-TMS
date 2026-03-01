/**
 * TRM (Tiny Recursive Model) API Client
 *
 * Provides methods for interacting with the TRM management API.
 */

import { api } from './api';

/**
 * Start TRM training
 * @param {Object} config - Training configuration
 * @returns {Promise} Training status
 */
export const startTraining = async (config) => {
  const response = await api.post('/trm/train', config);
  return response.data;
};

/**
 * Get training status
 * @returns {Promise} Current training status
 */
export const getTrainingStatus = async () => {
  const response = await api.get('/trm/training-status');
  return response.data;
};

/**
 * Load a TRM model
 * @param {string} modelPath - Path to model checkpoint
 * @param {string} device - Device (cpu or cuda)
 * @returns {Promise} Model info
 */
export const loadModel = async (modelPath, device = 'cpu') => {
  const response = await api.post('/trm/load-model', {
    model_path: modelPath,
    device: device
  });
  return response.data;
};

/**
 * Get current model info
 * @returns {Promise} Model information
 */
export const getModelInfo = async () => {
  const response = await api.get('/trm/model-info');
  return response.data;
};

/**
 * List available checkpoints
 * @param {string} checkpointDir - Checkpoint directory
 * @param {string} configId - Optional supply chain config ID to filter by
 * @returns {Promise} List of checkpoints
 */
export const listCheckpoints = async (checkpointDir = './checkpoints', configId = null) => {
  const params = { checkpoint_dir: checkpointDir };
  if (configId) {
    params.config_id = configId;
  }
  const response = await api.get('/trm/checkpoints', { params });
  return response.data;
};

/**
 * Test TRM model
 * @param {Object} testData - Test input data
 * @returns {Promise} Test results
 */
export const testModel = async (testData) => {
  const response = await api.post('/trm/test', testData);
  return response.data;
};

/**
 * Unload current model
 * @returns {Promise} Success message
 */
export const unloadModel = async () => {
  const response = await api.delete('/trm/model');
  return response.data;
};

/**
 * Get default TRM configuration
 * @returns {Promise} Default config
 */
export const getDefaultConfig = async () => {
  const response = await api.get('/trm/config');
  return response.data;
};

// ============================================================================
// Per-Site TRM Training API (Learning-Depth Curriculum)
// ============================================================================

/**
 * List sites with per-TRM training status
 * @param {number} configId - ADH training config ID
 * @returns {Promise} List of sites with training status
 */
export const listTrainingSites = async (configId) => {
  const response = await api.get(`/powell-training/configs/${configId}/sites`);
  return response.data;
};

/**
 * Train specific site
 * @param {number} configId - ADH training config ID
 * @param {number} siteId - Site ID to train
 * @param {Object} config - Training config (trm_types, phases, epochs)
 * @returns {Promise} Training results
 */
export const trainSite = async (configId, siteId, config = {}) => {
  const response = await api.post(`/powell-training/configs/${configId}/sites/${siteId}/train`, config);
  return response.data;
};

/**
 * Train all operational sites
 * @param {number} configId - ADH training config ID
 * @param {Object} config - Training config (trm_types, phases, epochs)
 * @returns {Promise} Training results
 */
export const trainAllSites = async (configId, config = {}) => {
  const response = await api.post(`/powell-training/configs/${configId}/train-all-sites`, config);
  return response.data;
};

/**
 * Get detailed training progress for a specific site
 * @param {number} configId - ADH training config ID
 * @param {number} siteId - Site ID
 * @returns {Promise} Detailed site progress
 */
export const getSiteProgress = async (configId, siteId) => {
  const response = await api.get(`/powell-training/configs/${configId}/sites/${siteId}/progress`);
  return response.data;
};

export default {
  startTraining,
  getTrainingStatus,
  loadModel,
  getModelInfo,
  listCheckpoints,
  testModel,
  unloadModel,
  getDefaultConfig,
  listTrainingSites,
  trainSite,
  trainAllSites,
  getSiteProgress
};
