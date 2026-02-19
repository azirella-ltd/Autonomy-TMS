/**
 * Formats a duration in seconds to MM:SS format
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted time string (MM:SS)
 */
export const formatDuration = (seconds) => {
  if (isNaN(seconds) || seconds < 0) return '00:00';
  
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

/**
 * Calculates the current score based on game state
 * @param {Object} player - The player object
 * @param {Object} game - The game object
 * @returns {number} The calculated score
 */
export const calculateScore = (player, game) => {
  if (!player || !game) return 0;
  
  // Base score on inventory, backlog, and other factors
  let score = 0;
  
  // Points for inventory (up to a certain limit)
  const maxInventoryScore = 100;
  const inventoryScore = Math.min(player.inventory || 0, 20) * 2; // 2 points per unit up to 20
  score += Math.min(inventoryScore, maxInventoryScore);
  
  // Penalty for backlog
  score -= (player.backlog || 0) * 5;
  
  // Bonus for completing orders
  score += (player.orders_completed || 0) * 10;
  
  // Bonus for game completion
  if (game.status === 'completed') {
    score += 50;
  }
  
  return Math.max(0, Math.round(score));
};

/**
 * Determines if a player can place an order
 * @param {Object} player - The player object
 * @param {number} amount - The amount to order
 * @returns {Object} { isValid: boolean, message: string }
 */
export const validateOrder = (player, amount) => {
  if (isNaN(amount) || amount < 0) {
    return { isValid: false, message: 'Please enter a valid positive number' };
  }
  
  if (amount > (player.inventory || 0) + (player.incoming_order || 0) + 10) {
    return { 
      isValid: false, 
      message: 'Order exceeds maximum allowed amount' 
    };
  }
  
  return { isValid: true, message: '' };
};

/**
 * Gets the color for a player based on their position or ID
 * @param {number} index - Player index or position
 * @returns {string} Tailwind CSS color class
 */
export const getPlayerColor = (index) => {
  const colors = [
    'bg-blue-100 text-blue-800',
    'bg-green-100 text-green-800',
    'bg-yellow-100 text-yellow-800',
    'bg-purple-100 text-purple-800',
    'bg-pink-100 text-pink-800',
    'bg-indigo-100 text-indigo-800',
  ];
  
  return colors[index % colors.length];
};

/**
 * Formats a timestamp to a readable time
 * @param {string} timestamp - ISO timestamp string
 * @returns {string} Formatted time (e.g., "2:30 PM")
 */
export const formatTime = (timestamp) => {
  if (!timestamp) return '';
  
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
};

/**
 * Gets the status badge for a game
 * @param {string} status - Game status
 * @returns {Object} { text: string, color: string }
 */
export const getGameStatusBadge = (status) => {
  switch (status) {
    case 'waiting':
      return { 
        text: 'Waiting for players', 
        color: 'bg-yellow-100 text-yellow-800' 
      };
    case 'in_progress':
      return { 
        text: 'In Progress', 
        color: 'bg-blue-100 text-blue-800' 
      };
    case 'paused':
      return { 
        text: 'Paused', 
        color: 'bg-gray-100 text-gray-800' 
      };
    case 'completed':
      return { 
        text: 'Completed', 
        color: 'bg-green-100 text-green-800' 
      };
    case 'cancelled':
      return { 
        text: 'Cancelled', 
        color: 'bg-red-100 text-red-800' 
      };
    default:
      return { 
        text: 'Unknown', 
        color: 'bg-gray-100 text-gray-800' 
      };
  }
};

/**
 * Calculates the progress percentage for the game
 * @param {Object} game - The game object
 * @returns {number} Progress percentage (0-100)
 */
export const calculateGameProgress = (game) => {
  if (!game || !game.current_round || !game.settings?.max_rounds) {
    return 0;
  }
  
  return Math.min(100, Math.round((game.current_round / game.settings.max_rounds) * 100));
};

/**
 * Gets the current round time remaining
 * @param {Object} game - The game object
 * @returns {number} Seconds remaining in the current round
 */
export const getRoundTimeRemaining = (game) => {
  if (!game || !game.round_ends_at) return 0;
  
  const now = new Date();
  const endTime = new Date(game.round_ends_at);
  const diff = Math.max(0, Math.floor((endTime - now) / 1000));
  
  return diff;
};

/**
 * Sorts players by score (descending)
 * @param {Array} players - Array of player objects
 * @returns {Array} Sorted array of players
 */
export const sortPlayersByScore = (players = []) => {
  return [...players].sort((a, b) => (b.score || 0) - (a.score || 0));
};

/**
 * Gets the current player's position in the game
 * @param {Object} game - The game object
 * @param {string} userId - The current user's ID
 * @returns {number} The player's position (1-based)
 */
export const getPlayerPosition = (game, userId) => {
  if (!game?.players?.length || !userId) return 0;
  
  const sortedPlayers = sortPlayersByScore(game.players);
  return sortedPlayers.findIndex(p => p.user_id === userId) + 1;
};

const gameUtils = {
  formatDuration,
  calculateScore,
  validateOrder,
  getPlayerColor,
  formatTime,
  getGameStatusBadge,
  calculateGameProgress,
  getRoundTimeRemaining,
  sortPlayersByScore,
  getPlayerPosition,
};

export default gameUtils;
