const STORAGE_KEY = 'adminDashboard:lastUrl';
const DEFAULT_PATH = '/admin?section=game&sc=all';

const getStorage = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  if (window.sessionStorage) {
    return window.sessionStorage;
  }
  if (window.localStorage) {
    return window.localStorage;
  }
  return null;
};

export const saveAdminDashboardPath = (path) => {
  if (typeof path !== 'string') return;
  if (!path.startsWith('/admin')) {
    return;
  }
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(STORAGE_KEY, path);
  } catch (err) {
    console.warn('Failed to persist admin dashboard path', err);
  }
};

export const getAdminDashboardPath = () => {
  const storage = getStorage();
  if (!storage) return DEFAULT_PATH;
  try {
    const stored = storage.getItem(STORAGE_KEY);
    if (stored && stored.startsWith('/admin')) {
      return stored;
    }
  } catch (err) {
    console.warn('Failed to read admin dashboard path', err);
  }
  return DEFAULT_PATH;
};

export const clearAdminDashboardPath = () => {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.warn('Failed to clear admin dashboard path', err);
  }
};

