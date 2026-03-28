/**
 * IdleWarning — Modal overlay shown 60 seconds before automatic logout
 * due to inactivity. Displays a countdown and allows the user to stay
 * logged in or log out immediately.
 *
 * IMPORTANT: The modal stops event propagation so that clicking within it
 * does NOT reset the activity timer (which would instantly dismiss the modal).
 * Only the "Stay Logged In" button explicitly resets timers.
 */

import React, { useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

const IdleWarning = () => {
  const { showTimeoutWarning, timeLeft, resetTimers, logout } = useAuth();

  const handleStayLoggedIn = useCallback((e) => {
    e.stopPropagation();
    resetTimers();
  }, [resetTimers]);

  const handleLogoutNow = useCallback((e) => {
    e.stopPropagation();
    logout();
  }, [logout]);

  // Prevent clicks on the modal from bubbling to the activity listeners
  const stopPropagation = useCallback((e) => {
    e.stopPropagation();
  }, []);

  if (!showTimeoutWarning) return null;

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onMouseDown={stopPropagation}
      onKeyDown={stopPropagation}
      onClick={stopPropagation}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-md w-full mx-4 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
            <svg
              className="w-5 h-5 text-yellow-600 dark:text-yellow-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Session Expiring
          </h3>
        </div>

        <p className="text-gray-600 dark:text-gray-300 mb-2">
          You will be logged out in{' '}
          <span className="font-bold text-yellow-600 dark:text-yellow-400 tabular-nums">
            {timeLeft}
          </span>{' '}
          {timeLeft === 1 ? 'second' : 'seconds'} due to inactivity.
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          Click "Stay Logged In" to continue your session.
        </p>

        {/* Progress bar */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mb-6">
          <div
            className="bg-yellow-500 h-1.5 rounded-full transition-all duration-1000 ease-linear"
            style={{ width: `${(timeLeft / 60) * 100}%` }}
          />
        </div>

        <div className="flex gap-3 justify-end">
          <button
            onClick={handleLogoutNow}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
          >
            Log Out Now
          </button>
          <button
            onClick={handleStayLoggedIn}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors"
          >
            Stay Logged In
          </button>
        </div>
      </div>
    </div>
  );
};

export default IdleWarning;
