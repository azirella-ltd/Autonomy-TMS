/**
 * Offline Mode Service
 * Phase 7 Sprint 1: Mobile Application
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import { apiClient } from './api';

const QUEUE_KEY = 'offline_queue';
const CACHE_KEY_PREFIX = 'cache_';

interface QueuedRequest {
  id: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  url: string;
  data?: any;
  timestamp: number;
  retryCount: number;
}

interface CacheEntry {
  data: any;
  timestamp: number;
  ttl: number; // Time to live in milliseconds
}

class OfflineService {
  private isOnline: boolean = true;
  private syncInProgress: boolean = false;
  private queue: QueuedRequest[] = [];
  private listeners: Set<(isOnline: boolean) => void> = new Set();

  /**
   * Initialize offline service
   */
  async initialize(): Promise<void> {
    // Load queue from storage
    await this.loadQueue();

    // Monitor network status
    NetInfo.addEventListener((state) => {
      const wasOnline = this.isOnline;
      this.isOnline = state.isConnected || false;

      console.log('Network status changed:', this.isOnline ? 'Online' : 'Offline');

      // Notify listeners
      this.notifyListeners(this.isOnline);

      // Sync queue when coming back online
      if (!wasOnline && this.isOnline) {
        this.syncQueue();
      }
    });

    // Initial network check
    const state = await NetInfo.fetch();
    this.isOnline = state.isConnected || false;

    console.log('Offline service initialized. Network:', this.isOnline ? 'Online' : 'Offline');
  }

  /**
   * Check if online
   */
  getIsOnline(): boolean {
    return this.isOnline;
  }

  /**
   * Add network status listener
   */
  addListener(callback: (isOnline: boolean) => void): void {
    this.listeners.add(callback);
  }

  /**
   * Remove network status listener
   */
  removeListener(callback: (isOnline: boolean) => void): void {
    this.listeners.delete(callback);
  }

  /**
   * Notify all listeners
   */
  private notifyListeners(isOnline: boolean): void {
    this.listeners.forEach((callback) => {
      try {
        callback(isOnline);
      } catch (error) {
        console.error('Error in network status listener:', error);
      }
    });
  }

  /**
   * Queue an API request for later execution
   */
  async queueRequest(
    method: QueuedRequest['method'],
    url: string,
    data?: any
  ): Promise<void> {
    const request: QueuedRequest = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      method,
      url,
      data,
      timestamp: Date.now(),
      retryCount: 0,
    };

    this.queue.push(request);
    await this.saveQueue();

    console.log(`Request queued: ${method} ${url}`);
  }

  /**
   * Load queue from storage
   */
  private async loadQueue(): Promise<void> {
    try {
      const queueJson = await AsyncStorage.getItem(QUEUE_KEY);
      if (queueJson) {
        this.queue = JSON.parse(queueJson);
        console.log(`Loaded ${this.queue.length} queued requests`);
      }
    } catch (error) {
      console.error('Failed to load offline queue:', error);
      this.queue = [];
    }
  }

  /**
   * Save queue to storage
   */
  private async saveQueue(): Promise<void> {
    try {
      await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(this.queue));
    } catch (error) {
      console.error('Failed to save offline queue:', error);
    }
  }

  /**
   * Sync queued requests
   */
  async syncQueue(): Promise<void> {
    if (!this.isOnline || this.syncInProgress || this.queue.length === 0) {
      return;
    }

    this.syncInProgress = true;
    console.log(`Syncing ${this.queue.length} queued requests...`);

    const successfulRequests: string[] = [];
    const failedRequests: QueuedRequest[] = [];

    for (const request of this.queue) {
      try {
        await this.executeRequest(request);
        successfulRequests.push(request.id);
        console.log(`Synced request: ${request.method} ${request.url}`);
      } catch (error) {
        console.error(`Failed to sync request: ${request.method} ${request.url}`, error);
        request.retryCount++;

        // Retry up to 3 times
        if (request.retryCount < 3) {
          failedRequests.push(request);
        } else {
          console.error('Max retries reached, discarding request');
        }
      }
    }

    // Update queue - keep only failed requests
    this.queue = failedRequests;
    await this.saveQueue();

    this.syncInProgress = false;
    console.log(`Sync complete. Success: ${successfulRequests.length}, Failed: ${failedRequests.length}`);
  }

  /**
   * Execute a queued request
   */
  private async executeRequest(request: QueuedRequest): Promise<void> {
    const { method, url, data } = request;

    switch (method) {
      case 'GET':
        await apiClient.get(url);
        break;
      case 'POST':
        await apiClient.post(url, data);
        break;
      case 'PUT':
        await apiClient.put(url, data);
        break;
      case 'DELETE':
        await apiClient.delete(url);
        break;
    }
  }

  /**
   * Get queue size
   */
  getQueueSize(): number {
    return this.queue.length;
  }

  /**
   * Clear queue
   */
  async clearQueue(): Promise<void> {
    this.queue = [];
    await AsyncStorage.removeItem(QUEUE_KEY);
    console.log('Offline queue cleared');
  }

  /**
   * Cache data
   */
  async cacheData(key: string, data: any, ttl: number = 3600000): Promise<void> {
    try {
      const cacheEntry: CacheEntry = {
        data,
        timestamp: Date.now(),
        ttl,
      };

      await AsyncStorage.setItem(
        `${CACHE_KEY_PREFIX}${key}`,
        JSON.stringify(cacheEntry)
      );

      console.log(`Cached data: ${key}`);
    } catch (error) {
      console.error('Failed to cache data:', error);
    }
  }

  /**
   * Get cached data
   */
  async getCachedData<T = any>(key: string): Promise<T | null> {
    try {
      const cacheJson = await AsyncStorage.getItem(`${CACHE_KEY_PREFIX}${key}`);

      if (!cacheJson) {
        return null;
      }

      const cacheEntry: CacheEntry = JSON.parse(cacheJson);

      // Check if cache is expired
      const age = Date.now() - cacheEntry.timestamp;
      if (age > cacheEntry.ttl) {
        console.log(`Cache expired: ${key}`);
        await this.clearCachedData(key);
        return null;
      }

      console.log(`Cache hit: ${key}`);
      return cacheEntry.data as T;
    } catch (error) {
      console.error('Failed to get cached data:', error);
      return null;
    }
  }

  /**
   * Clear cached data
   */
  async clearCachedData(key: string): Promise<void> {
    try {
      await AsyncStorage.removeItem(`${CACHE_KEY_PREFIX}${key}`);
      console.log(`Cache cleared: ${key}`);
    } catch (error) {
      console.error('Failed to clear cached data:', error);
    }
  }

  /**
   * Clear all cached data
   */
  async clearAllCache(): Promise<void> {
    try {
      const keys = await AsyncStorage.getAllKeys();
      const cacheKeys = keys.filter((key) => key.startsWith(CACHE_KEY_PREFIX));
      await AsyncStorage.multiRemove(cacheKeys);
      console.log(`Cleared ${cacheKeys.length} cache entries`);
    } catch (error) {
      console.error('Failed to clear all cache:', error);
    }
  }

  /**
   * Get cache statistics
   */
  async getCacheStats(): Promise<{
    count: number;
    totalSize: number;
    keys: string[];
  }> {
    try {
      const keys = await AsyncStorage.getAllKeys();
      const cacheKeys = keys.filter((key) => key.startsWith(CACHE_KEY_PREFIX));

      // Calculate total size (approximate)
      let totalSize = 0;
      for (const key of cacheKeys) {
        const value = await AsyncStorage.getItem(key);
        if (value) {
          totalSize += value.length;
        }
      }

      return {
        count: cacheKeys.length,
        totalSize,
        keys: cacheKeys.map((key) => key.replace(CACHE_KEY_PREFIX, '')),
      };
    } catch (error) {
      console.error('Failed to get cache stats:', error);
      return { count: 0, totalSize: 0, keys: [] };
    }
  }
}

// Export singleton instance
export const offlineService = new OfflineService();
export default offlineService;
