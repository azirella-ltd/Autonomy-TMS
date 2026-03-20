/**
 * AzirellaAvatar — Floating AI assistant avatar.
 *
 * A circular avatar using the Azirella gazelle constellation logo.
 * Every ~15 seconds, the gazelle picks up its head and turns toward
 * the user (subtle CSS animation), then settles back.
 *
 * Click opens the Talk to Me popup.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils/cn';

const AzirellaAvatar = ({ onClick, size = 56, className, showPulse = true }) => {
  const [isLooking, setIsLooking] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  // Periodically "look up" — the gazelle raises its head
  useEffect(() => {
    const scheduleNext = () => {
      // Random interval between 12-20 seconds
      const delay = 12000 + Math.random() * 8000;
      return setTimeout(() => {
        setIsLooking(true);
        // Hold the look for 2-3 seconds
        setTimeout(() => setIsLooking(false), 2000 + Math.random() * 1000);
        timerId = scheduleNext();
      }, delay);
    };

    let timerId = scheduleNext();
    return () => clearTimeout(timerId);
  }, []);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'fixed bottom-6 right-6 z-50',
        'rounded-full shadow-lg hover:shadow-xl',
        'transition-all duration-300 ease-out',
        'focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2',
        isHovered ? 'scale-110' : '',
        className,
      )}
      style={{ width: size, height: size }}
      aria-label="Talk to Azirella"
      title="Talk to me"
    >
      {/* Outer glow ring */}
      {showPulse && (
        <span className="absolute inset-0 rounded-full animate-ping bg-violet-400/20" style={{ animationDuration: '3s' }} />
      )}

      {/* Avatar container with animation */}
      <div
        className={cn(
          'relative w-full h-full rounded-full overflow-hidden',
          'bg-gradient-to-br from-purple-900 via-violet-800 to-indigo-900',
          'border-2 transition-all duration-700 ease-in-out',
          isHovered ? 'border-violet-400 shadow-violet-400/30' : 'border-violet-500/40',
        )}
        style={{
          // The "look up" animation — slight rotation and translate
          transform: isLooking
            ? 'rotate(-8deg) translateY(-2px)'
            : isHovered
              ? 'rotate(-3deg)'
              : 'rotate(0deg)',
          transition: 'transform 0.7s cubic-bezier(0.34, 1.56, 0.64, 1)',
        }}
      >
        {/* Gazelle constellation image */}
        <img
          src="/Azirella_logo.png"
          alt="Azirella"
          className="absolute"
          style={{
            // Position to show just the gazelle head area
            width: '180%',
            height: '180%',
            top: '-15%',
            left: '-45%',
            objectFit: 'cover',
            filter: 'brightness(1.3) contrast(1.1)',
            // Subtle head-raise effect
            transform: isLooking
              ? 'scale(1.05) translateY(-3px)'
              : 'scale(1)',
            transition: 'transform 0.7s cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}
          draggable={false}
        />

        {/* Constellation sparkle overlay */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: isLooking
              ? 'radial-gradient(circle at 60% 30%, rgba(167,139,250,0.3) 0%, transparent 60%)'
              : 'radial-gradient(circle at 50% 50%, rgba(167,139,250,0.1) 0%, transparent 60%)',
            transition: 'background 0.7s ease',
          }}
        />
      </div>

      {/* Status dot — shows the AI is active */}
      <span className={cn(
        'absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full border-2 border-white',
        'bg-emerald-400',
      )} />
    </button>
  );
};

export default AzirellaAvatar;
