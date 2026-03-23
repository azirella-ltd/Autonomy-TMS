/**
 * useNavStore — Zustand store for the two-tier navigation bar.
 *
 * Tracks which top-level category is currently active (expanded in Tier 2).
 * Persists to sessionStorage so the active category survives page refresh.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const useNavStore = create(
  persist(
    (set) => ({
      activeCategoryId: null,

      setActiveCategory: (id) => set({ activeCategoryId: id }),
    }),
    {
      name: 'autonomy-nav-category',
      storage: {
        getItem: (name) => {
          const str = sessionStorage.getItem(name);
          return str ? JSON.parse(str) : null;
        },
        setItem: (name, value) => sessionStorage.setItem(name, JSON.stringify(value)),
        removeItem: (name) => sessionStorage.removeItem(name),
      },
      partialize: (state) => ({
        activeCategoryId: state.activeCategoryId,
      }),
    },
  ),
);

export default useNavStore;
