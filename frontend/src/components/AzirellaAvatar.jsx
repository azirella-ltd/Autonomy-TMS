/**
 * AzirellaAvatar — Floating AI assistant avatar with voice support.
 *
 * Visual states driven by VoiceState:
 *   IDLE/PASSIVE — subtle periodic head-raise, gentle pulse ring
 *   WAKE         — bright glow, quick head-raise, chime plays
 *   LISTENING    — ears up, pulsing ring synced to voice, border glows
 *   PROCESSING   — thinking animation, rotating ring
 *   SPEAKING     — mouth moves (scale pulse), blue glow
 *
 * Click: opens Talk to Me popup
 * "Hey Autonomy": activates voice flow
 */

import React, { useState, useEffect } from 'react';
import { cn } from '../lib/utils/cn';
import { VoiceState } from '../hooks/useVoiceAssistant';

const STATE_STYLES = {
  [VoiceState.IDLE]: {
    borderColor: 'border-violet-500/30',
    ringColor: 'ring-violet-400/10',
    glowShadow: 'none',
    rotate: 0,
    scale: 1,
  },
  [VoiceState.PASSIVE]: {
    borderColor: 'border-violet-500/40',
    ringColor: 'ring-violet-400/20',
    glowShadow: 'none',
    rotate: 0,
    scale: 1,
  },
  [VoiceState.WAKE]: {
    borderColor: 'border-violet-400',
    ringColor: 'ring-violet-400/40',
    glowShadow: '0 0 20px rgba(139,92,246,0.5)',
    rotate: -12,
    scale: 1.15,
  },
  [VoiceState.LISTENING]: {
    borderColor: 'border-green-400',
    ringColor: 'ring-green-400/30',
    glowShadow: '0 0 24px rgba(74,222,128,0.4)',
    rotate: -8,
    scale: 1.08,
  },
  [VoiceState.PROCESSING]: {
    borderColor: 'border-amber-400',
    ringColor: 'ring-amber-400/30',
    glowShadow: '0 0 16px rgba(251,191,36,0.4)',
    rotate: -5,
    scale: 1.05,
  },
  [VoiceState.SPEAKING]: {
    borderColor: 'border-blue-400',
    ringColor: 'ring-blue-400/30',
    glowShadow: '0 0 20px rgba(96,165,250,0.4)',
    rotate: -6,
    scale: 1.05,
  },
};

const STATUS_COLORS = {
  [VoiceState.IDLE]: 'bg-gray-400',
  [VoiceState.PASSIVE]: 'bg-emerald-400',
  [VoiceState.WAKE]: 'bg-violet-400 animate-pulse',
  [VoiceState.LISTENING]: 'bg-green-400 animate-pulse',
  [VoiceState.PROCESSING]: 'bg-amber-400 animate-spin',
  [VoiceState.SPEAKING]: 'bg-blue-400 animate-pulse',
};

const STATUS_LABELS = {
  [VoiceState.IDLE]: '',
  [VoiceState.PASSIVE]: '',
  [VoiceState.WAKE]: 'Heard you!',
  [VoiceState.LISTENING]: 'Listening...',
  [VoiceState.PROCESSING]: 'Thinking...',
  [VoiceState.SPEAKING]: 'Speaking...',
};

const AzirellaAvatar = ({
  onClick,
  voiceState = VoiceState.IDLE,
  transcript = '',
  interimTranscript = '',
  size = 56,
  className,
}) => {
  const [isIdleLooking, setIsIdleLooking] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [speakPulse, setSpeakPulse] = useState(false);

  // Periodic head-raise in passive/idle state
  useEffect(() => {
    if (voiceState !== VoiceState.PASSIVE && voiceState !== VoiceState.IDLE) {
      setIsIdleLooking(false);
      return;
    }
    const scheduleNext = () => {
      const delay = 12000 + Math.random() * 8000;
      return setTimeout(() => {
        setIsIdleLooking(true);
        setTimeout(() => setIsIdleLooking(false), 2000 + Math.random() * 1000);
        timerId = scheduleNext();
      }, delay);
    };
    let timerId = scheduleNext();
    return () => clearTimeout(timerId);
  }, [voiceState]);

  // Speaking pulse (mouth movement simulation)
  useEffect(() => {
    if (voiceState !== VoiceState.SPEAKING) {
      setSpeakPulse(false);
      return;
    }
    const interval = setInterval(() => {
      setSpeakPulse(p => !p);
    }, 300);
    return () => clearInterval(interval);
  }, [voiceState]);

  const styles = STATE_STYLES[voiceState] || STATE_STYLES[VoiceState.IDLE];
  const isActive = voiceState !== VoiceState.IDLE && voiceState !== VoiceState.PASSIVE;
  const showLabel = STATUS_LABELS[voiceState];
  const showTranscript = voiceState === VoiceState.LISTENING && (transcript || interimTranscript);

  // Determine rotation — active states override idle animation
  const rotation = isActive
    ? styles.rotate
    : isIdleLooking
      ? -8
      : isHovered
        ? -3
        : 0;

  const scale = isActive
    ? styles.scale * (speakPulse ? 1.03 : 1)
    : isHovered
      ? 1.1
      : 1;

  return (
    <div className={cn('fixed bottom-6 right-6 z-50', className)}>
      {/* Transcript bubble (visible during listening) */}
      {showTranscript && (
        <div className="absolute bottom-full right-0 mb-2 max-w-64 bg-popover border border-border rounded-lg shadow-lg px-3 py-2 text-xs text-foreground animate-in fade-in slide-in-from-bottom-2">
          {transcript && <span className="font-medium">{transcript}</span>}
          {interimTranscript && (
            <span className="text-muted-foreground italic"> {interimTranscript}</span>
          )}
        </div>
      )}

      {/* Status label (wake/listening/processing/speaking) */}
      {showLabel && (
        <div className="absolute bottom-full right-0 mb-2 px-2.5 py-1 rounded-full text-[10px] font-medium bg-popover border border-border shadow-sm whitespace-nowrap animate-in fade-in">
          {showLabel}
        </div>
      )}

      {/* Avatar button */}
      <button
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={cn(
          'rounded-full shadow-lg hover:shadow-xl',
          'transition-all duration-300 ease-out',
          'focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2',
        )}
        style={{ width: size, height: size }}
        aria-label="Talk to Azirella"
        title={isActive ? STATUS_LABELS[voiceState] : 'Talk to me'}
      >
        {/* Outer ring — pulsing in active states */}
        {(isActive || voiceState === VoiceState.PASSIVE) && (
          <span
            className={cn(
              'absolute inset-0 rounded-full',
              isActive ? 'animate-ping' : 'animate-ping',
            )}
            style={{
              animationDuration: isActive ? '1.5s' : '3s',
              backgroundColor: voiceState === VoiceState.LISTENING
                ? 'rgba(74,222,128,0.15)'
                : voiceState === VoiceState.WAKE
                  ? 'rgba(139,92,246,0.2)'
                  : voiceState === VoiceState.SPEAKING
                    ? 'rgba(96,165,250,0.15)'
                    : voiceState === VoiceState.PROCESSING
                      ? 'rgba(251,191,36,0.15)'
                      : 'rgba(139,92,246,0.1)',
            }}
          />
        )}

        {/* Avatar container */}
        <div
          className={cn(
            'relative w-full h-full rounded-full overflow-hidden',
            'bg-gradient-to-br from-purple-900 via-violet-800 to-indigo-900',
            'border-2 transition-all duration-500',
            styles.borderColor,
          )}
          style={{
            transform: `rotate(${rotation}deg) scale(${scale})`,
            transition: 'transform 0.7s cubic-bezier(0.34, 1.56, 0.64, 1)',
            boxShadow: styles.glowShadow,
          }}
        >
          {/* Gazelle constellation image */}
          <img
            src="/Azirella_logo.png"
            alt="Azirella"
            className="absolute pointer-events-none"
            style={{
              width: '180%',
              height: '180%',
              top: '-15%',
              left: '-45%',
              objectFit: 'cover',
              filter: isActive ? 'brightness(1.5) contrast(1.2)' : 'brightness(1.3) contrast(1.1)',
              transform: isActive
                ? `scale(1.05) translateY(-3px)`
                : isIdleLooking
                  ? 'scale(1.05) translateY(-3px)'
                  : 'scale(1)',
              transition: 'transform 0.7s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.5s ease',
            }}
            draggable={false}
          />

          {/* Constellation sparkle overlay */}
          <div
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{
              background: isActive
                ? 'radial-gradient(circle at 60% 30%, rgba(167,139,250,0.4) 0%, transparent 60%)'
                : isIdleLooking
                  ? 'radial-gradient(circle at 60% 30%, rgba(167,139,250,0.3) 0%, transparent 60%)'
                  : 'radial-gradient(circle at 50% 50%, rgba(167,139,250,0.1) 0%, transparent 60%)',
              transition: 'background 0.7s ease',
            }}
          />
        </div>

        {/* Status dot */}
        <span className={cn(
          'absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full border-2 border-white transition-colors',
          STATUS_COLORS[voiceState] || 'bg-gray-400',
        )} />
      </button>
    </div>
  );
};

export default AzirellaAvatar;
