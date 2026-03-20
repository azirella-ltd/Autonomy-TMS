/**
 * AzirellaAvatar — Floating AI assistant with XPeng-style liveliness.
 *
 * The gazelle constellation feels ALIVE:
 *   - Always subtly moving (breathing sway, gentle float)
 *   - Constellation nodes twinkle randomly
 *   - Periodically looks up and toward the user
 *   - Reacts expressively to voice states
 *
 * Built from the Azirella logo PNG with CSS transforms for animation.
 * No "Azirella" text shown — just the constellation figure.
 */

import React, { useState, useEffect, useRef } from 'react';
import { cn } from '../lib/utils/cn';
import { VoiceState } from '../hooks/useVoiceAssistant';

// ── Per-state visual config ───────────────────────────────────────────────

const STATES = {
  [VoiceState.IDLE]: {
    border: 'border-violet-500/30',
    glow: 'none',
    imgBrightness: 1.2,
  },
  [VoiceState.PASSIVE]: {
    border: 'border-violet-500/40',
    glow: '0 0 8px rgba(139,92,246,0.2)',
    imgBrightness: 1.3,
  },
  [VoiceState.WAKE]: {
    border: 'border-violet-400',
    glow: '0 0 28px rgba(139,92,246,0.6)',
    imgBrightness: 1.6,
  },
  [VoiceState.LISTENING]: {
    border: 'border-green-400',
    glow: '0 0 28px rgba(74,222,128,0.5)',
    imgBrightness: 1.5,
  },
  [VoiceState.PROCESSING]: {
    border: 'border-amber-400',
    glow: '0 0 20px rgba(251,191,36,0.5)',
    imgBrightness: 1.4,
  },
  [VoiceState.SPEAKING]: {
    border: 'border-blue-400',
    glow: '0 0 24px rgba(96,165,250,0.5)',
    imgBrightness: 1.5,
  },
};

const STATUS_DOT = {
  [VoiceState.IDLE]: 'bg-gray-400',
  [VoiceState.PASSIVE]: 'bg-emerald-400',
  [VoiceState.WAKE]: 'bg-violet-400',
  [VoiceState.LISTENING]: 'bg-green-400',
  [VoiceState.PROCESSING]: 'bg-amber-400',
  [VoiceState.SPEAKING]: 'bg-blue-400',
};

const STATUS_LABEL = {
  [VoiceState.WAKE]: 'Heard you!',
  [VoiceState.LISTENING]: 'Listening…',
  [VoiceState.PROCESSING]: 'Thinking…',
  [VoiceState.SPEAKING]: 'Speaking…',
};

// ── Component ─────────────────────────────────────────────────────────────

const AzirellaAvatar = ({
  onClick,
  voiceState = VoiceState.IDLE,
  transcript = '',
  interimTranscript = '',
  size = 80,
  className,
}) => {
  const [hovered, setHovered] = useState(false);
  const [breathPhase, setBreathPhase] = useState(0);    // 0-360 continuous
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [twinkle, setTwinkle] = useState(0);             // random sparkle seed
  const [speakBeat, setSpeakBeat] = useState(false);
  const frameRef = useRef(0);

  const isActive = ![VoiceState.IDLE, VoiceState.PASSIVE].includes(voiceState);
  const cfg = STATES[voiceState] || STATES[VoiceState.IDLE];
  const label = STATUS_LABEL[voiceState];
  const showTranscript = voiceState === VoiceState.LISTENING && (transcript || interimTranscript);

  // ── Breathing animation (continuous gentle sway) ────────────────────
  useEffect(() => {
    let raf;
    const tick = () => {
      frameRef.current += 1;
      // Slow sine wave — completes one cycle every ~6 seconds
      setBreathPhase(frameRef.current * 0.5);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // ── Periodic look-up (every 12-20s in passive/idle) ─────────────────
  useEffect(() => {
    if (isActive) { setIsLookingUp(false); return; }
    const schedule = () => {
      const delay = 12000 + Math.random() * 8000;
      return setTimeout(() => {
        setIsLookingUp(true);
        setTimeout(() => setIsLookingUp(false), 2500 + Math.random() * 1500);
        tid = schedule();
      }, delay);
    };
    let tid = schedule();
    return () => clearTimeout(tid);
  }, [isActive]);

  // ── Constellation twinkle (random sparkle every 2-4s) ───────────────
  useEffect(() => {
    const interval = setInterval(() => {
      setTwinkle(Math.random());
    }, 2000 + Math.random() * 2000);
    return () => clearInterval(interval);
  }, []);

  // ── Speaking beat pulse ─────────────────────────────────────────────
  useEffect(() => {
    if (voiceState !== VoiceState.SPEAKING) { setSpeakBeat(false); return; }
    const interval = setInterval(() => setSpeakBeat(b => !b), 280);
    return () => clearInterval(interval);
  }, [voiceState]);

  // ── Compute transforms ──────────────────────────────────────────────

  // Breathing: gentle vertical float + slight rotation
  const breathY = Math.sin(breathPhase * Math.PI / 180) * 2;    // ±2px float
  const breathR = Math.sin(breathPhase * 0.7 * Math.PI / 180) * 1.5; // ±1.5° sway

  // Look-up: head raises, rotates toward user
  const lookY = isLookingUp ? -5 : 0;
  const lookR = isLookingUp ? -10 : 0;

  // Active state transforms
  const activeY = voiceState === VoiceState.WAKE ? -6
    : voiceState === VoiceState.LISTENING ? -4
    : voiceState === VoiceState.SPEAKING ? (speakBeat ? -2 : 0)
    : 0;
  const activeR = voiceState === VoiceState.WAKE ? -14
    : voiceState === VoiceState.LISTENING ? -8
    : voiceState === VoiceState.PROCESSING ? -5 + Math.sin(breathPhase * 2 * Math.PI / 180) * 3
    : voiceState === VoiceState.SPEAKING ? -6
    : 0;
  const activeS = voiceState === VoiceState.WAKE ? 1.12
    : voiceState === VoiceState.SPEAKING ? (speakBeat ? 1.06 : 1.02)
    : isActive ? 1.05
    : 1;

  // Final composite
  const finalY = isActive ? activeY : breathY + lookY;
  const finalR = isActive ? activeR : breathR + lookR;
  const finalS = isActive ? activeS : (hovered ? 1.08 : 1) + (isLookingUp ? 0.03 : 0);

  // Twinkle overlay position (random sparkle point)
  const twinkleX = 30 + twinkle * 40; // 30-70% from left
  const twinkleY = 20 + (1 - twinkle) * 40; // 20-60% from top

  return (
    <div className={cn('fixed bottom-6 right-6 z-50', className)}>

      {/* Transcript bubble */}
      {showTranscript && (
        <div className="absolute bottom-full right-0 mb-3 max-w-72 bg-popover border border-border rounded-xl shadow-xl px-3.5 py-2.5 text-xs text-foreground animate-in fade-in slide-in-from-bottom-2">
          {transcript && <span className="font-medium">{transcript}</span>}
          {interimTranscript && <span className="text-muted-foreground italic"> {interimTranscript}</span>}
        </div>
      )}

      {/* Status label */}
      {label && !showTranscript && (
        <div className="absolute bottom-full right-0 mb-3 px-3 py-1.5 rounded-full text-[11px] font-medium bg-popover border border-border shadow-md whitespace-nowrap animate-in fade-in slide-in-from-bottom-1">
          <span className={cn(
            'inline-block w-1.5 h-1.5 rounded-full mr-1.5',
            STATUS_DOT[voiceState],
            isActive ? 'animate-pulse' : '',
          )} />
          {label}
        </div>
      )}

      {/* Avatar button */}
      <button
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className="relative rounded-full focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
        style={{ width: size, height: size }}
        aria-label="Talk to Azirella"
        title={label || 'Talk to me'}
      >
        {/* Outer pulse ring */}
        <span
          className="absolute inset-0 rounded-full animate-ping pointer-events-none"
          style={{
            animationDuration: isActive ? '1.2s' : '4s',
            opacity: isActive ? 0.6 : 0.3,
            backgroundColor: voiceState === VoiceState.LISTENING ? 'rgba(74,222,128,0.15)'
              : voiceState === VoiceState.WAKE ? 'rgba(139,92,246,0.25)'
              : voiceState === VoiceState.SPEAKING ? 'rgba(96,165,250,0.15)'
              : voiceState === VoiceState.PROCESSING ? 'rgba(251,191,36,0.15)'
              : 'rgba(139,92,246,0.08)',
          }}
        />

        {/* Main circle */}
        <div
          className={cn(
            'relative w-full h-full rounded-full overflow-hidden',
            'bg-gradient-to-br from-purple-950 via-violet-900 to-indigo-950',
            'border-2 shadow-lg',
            cfg.border,
          )}
          style={{
            transform: `translateY(${finalY}px) rotate(${finalR}deg) scale(${finalS})`,
            transition: isActive
              ? 'transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.4s ease'
              : 'transform 0.8s cubic-bezier(0.25, 0.46, 0.45, 0.94), box-shadow 0.6s ease',
            boxShadow: cfg.glow,
          }}
        >
          {/* Gazelle constellation — full body, text clipped */}
          <img
            src="/Azirella_logo.png"
            alt=""
            className="absolute pointer-events-none select-none"
            style={{
              width: '250%',
              height: '250%',
              top: '-40%',
              left: '-20%',
              objectFit: 'cover',
              clipPath: 'inset(0 40% 0 0)',
              filter: `brightness(${cfg.imgBrightness}) contrast(1.15)`,
              transition: 'filter 0.5s ease',
            }}
            draggable={false}
          />

          {/* Constellation twinkle sparkle */}
          <div
            className="absolute rounded-full pointer-events-none"
            style={{
              width: 4,
              height: 4,
              top: `${twinkleY}%`,
              left: `${twinkleX}%`,
              background: 'white',
              boxShadow: '0 0 6px 2px rgba(255,255,255,0.8)',
              opacity: 0.7 + twinkle * 0.3,
              transition: 'opacity 0.3s ease, top 0.5s ease, left 0.5s ease',
            }}
          />
          {/* Second sparkle at offset position */}
          <div
            className="absolute rounded-full pointer-events-none"
            style={{
              width: 3,
              height: 3,
              top: `${70 - twinkleY}%`,
              left: `${60 - twinkleX + 20}%`,
              background: 'rgba(167,139,250,0.9)',
              boxShadow: '0 0 4px 1px rgba(167,139,250,0.6)',
              opacity: 0.5 + (1 - twinkle) * 0.5,
              transition: 'opacity 0.4s ease, top 0.6s ease, left 0.6s ease',
            }}
          />

          {/* Gradient overlay — shifts with state */}
          <div
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{
              background: isActive
                ? `radial-gradient(circle at 55% 30%, rgba(167,139,250,0.35) 0%, transparent 65%)`
                : isLookingUp
                  ? 'radial-gradient(circle at 55% 25%, rgba(167,139,250,0.25) 0%, transparent 60%)'
                  : 'radial-gradient(circle at 50% 50%, rgba(167,139,250,0.08) 0%, transparent 60%)',
              transition: 'background 0.8s ease',
            }}
          />

          {/* Processing spinner ring */}
          {voiceState === VoiceState.PROCESSING && (
            <div
              className="absolute inset-1 rounded-full border-2 border-transparent border-t-amber-400/60 pointer-events-none"
              style={{
                animation: 'spin 1.2s linear infinite',
              }}
            />
          )}
        </div>

        {/* Status dot */}
        <span className={cn(
          'absolute bottom-0.5 right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white transition-colors duration-300',
          STATUS_DOT[voiceState] || 'bg-gray-400',
          isActive ? 'animate-pulse' : '',
        )} />
      </button>
    </div>
  );
};

export default AzirellaAvatar;
