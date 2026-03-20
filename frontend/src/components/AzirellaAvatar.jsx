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
  size = 96,
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
          {/* Azirella human constellation — inline SVG with animated head + arm */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 120 120"
            fill="none"
            className="absolute inset-0 w-full h-full pointer-events-none select-none"
            style={{
              filter: `brightness(${cfg.imgBrightness}) contrast(1.1)`,
              transition: 'filter 0.5s ease',
            }}
          >
            <defs>
              <linearGradient id="av-bg" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#2e1065"/>
                <stop offset="50%" stopColor="#4c1d95"/>
                <stop offset="100%" stopColor="#312e81"/>
              </linearGradient>
              <linearGradient id="av-ln" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#c4b5fd" stopOpacity="0.7"/>
                <stop offset="100%" stopColor="#818cf8" stopOpacity="0.35"/>
              </linearGradient>
              <radialGradient id="av-sg">
                <stop offset="0%" stopColor="#f5f3ff" stopOpacity="1"/>
                <stop offset="50%" stopColor="#c4b5fd" stopOpacity="0.6"/>
                <stop offset="100%" stopColor="#7c3aed" stopOpacity="0"/>
              </radialGradient>
              <filter id="av-gl">
                <feGaussianBlur stdDeviation="1.2" result="b"/>
                <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
            </defs>

            {/* Background stars */}
            <circle cx="18" cy="22" r="0.7" fill="white" opacity="0.2"/>
            <circle cx="95" cy="18" r="0.5" fill="white" opacity="0.15"/>
            <circle cx="12" cy="70" r="0.6" fill="white" opacity="0.18"/>
            <circle cx="100" cy="80" r="0.5" fill="white" opacity="0.12"/>
            <circle cx="30" cy="100" r="0.6" fill="white" opacity="0.15"/>
            <circle cx="50" cy="12" r="0.5" fill="white" opacity="0.12"/>

            <g filter="url(#av-gl)">
              {/* ── BODY (static) ── */}
              <line x1="50" y1="55" x2="65" y2="42" stroke="url(#av-ln)" strokeWidth="1"/>
              <line x1="50" y1="55" x2="42" y2="65" stroke="url(#av-ln)" strokeWidth="1"/>
              <line x1="42" y1="65" x2="32" y2="58" stroke="url(#av-ln)" strokeWidth="0.8"/>
              <line x1="50" y1="55" x2="55" y2="62" stroke="url(#av-ln)" strokeWidth="0.7" opacity="0.5"/>
              <line x1="42" y1="65" x2="38" y2="80" stroke="url(#av-ln)" strokeWidth="0.9"/>
              <line x1="42" y1="65" x2="48" y2="80" stroke="url(#av-ln)" strokeWidth="0.9"/>
              <line x1="38" y1="80" x2="35" y2="98" stroke="url(#av-ln)" strokeWidth="0.7"/>
              <line x1="48" y1="80" x2="52" y2="98" stroke="url(#av-ln)" strokeWidth="0.7"/>
              <line x1="55" y1="62" x2="60" y2="80" stroke="url(#av-ln)" strokeWidth="0.9"/>
              <line x1="60" y1="80" x2="62" y2="98" stroke="url(#av-ln)" strokeWidth="0.7"/>

              {/* Body nodes */}
              <circle cx="50" cy="55" r="2.5" fill="url(#av-sg)" opacity="0.8"/>
              <circle cx="50" cy="55" r="1.2" fill="white" opacity="0.9"/>
              <circle cx="42" cy="65" r="2.5" fill="url(#av-sg)" opacity="0.75"/>
              <circle cx="42" cy="65" r="1.2" fill="white" opacity="0.85"/>
              <circle cx="32" cy="58" r="1.8" fill="url(#av-sg)" opacity="0.55"/>
              <circle cx="32" cy="58" r="0.9" fill="white" opacity="0.7"/>
              <circle cx="55" cy="62" r="2" fill="url(#av-sg)" opacity="0.65"/>
              <circle cx="55" cy="62" r="1" fill="white" opacity="0.8"/>
              <circle cx="38" cy="80" r="1.8" fill="url(#av-sg)" opacity="0.6"/>
              <circle cx="38" cy="80" r="0.9" fill="white" opacity="0.75"/>
              <circle cx="48" cy="80" r="1.8" fill="url(#av-sg)" opacity="0.6"/>
              <circle cx="48" cy="80" r="0.9" fill="white" opacity="0.75"/>
              <circle cx="35" cy="98" r="1.3" fill="url(#av-sg)" opacity="0.45"/>
              <circle cx="35" cy="98" r="0.7" fill="white" opacity="0.6"/>
              <circle cx="52" cy="98" r="1.3" fill="url(#av-sg)" opacity="0.45"/>
              <circle cx="52" cy="98" r="0.7" fill="white" opacity="0.6"/>
              <circle cx="60" cy="80" r="1.8" fill="url(#av-sg)" opacity="0.6"/>
              <circle cx="60" cy="80" r="0.9" fill="white" opacity="0.75"/>
              <circle cx="62" cy="98" r="1.3" fill="url(#av-sg)" opacity="0.45"/>
              <circle cx="62" cy="98" r="0.7" fill="white" opacity="0.6"/>

              {/* ── FORELEG (animated — lifts) ── */}
              <g style={{
                transformOrigin: '55px 40px',
                transform: `rotate(${isActive ? -25 : isLookingUp ? -15 : 0}deg)`,
                transition: 'transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)',
              }}>
                <line x1="65" y1="42" x2="72" y2="55" stroke="url(#av-ln)" strokeWidth="0.9"/>
                <line x1="72" y1="55" x2="75" y2="72" stroke="url(#av-ln)" strokeWidth="0.7"/>
                <circle cx="72" cy="55" r="1.8" fill="url(#av-sg)" opacity="0.65"/>
                <circle cx="72" cy="55" r="0.9" fill="white" opacity="0.8"/>
                <circle cx="75" cy="72" r="1.5" fill="url(#av-sg)" opacity="0.5"/>
                <circle cx="75" cy="72" r="0.8" fill="white" opacity="0.65"/>
              </g>

              {/* ── HEAD + NECK (animated — turns toward user) ── */}
              <g style={{
                transformOrigin: '38px 30px',
                transform: `rotate(${isActive ? -15 : isLookingUp ? -10 : 0}deg) translateY(${isActive ? -3 : isLookingUp ? -2 : 0}px)`,
                transition: 'transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)',
              }}>
                <line x1="65" y1="42" x2="72" y2="28" stroke="url(#av-ln)" strokeWidth="1.1"/>
                <line x1="72" y1="28" x2="82" y2="22" stroke="url(#av-ln)" strokeWidth="1"/>
                <line x1="72" y1="28" x2="68" y2="18" stroke="url(#av-ln)" strokeWidth="0.7"/>
                <line x1="72" y1="28" x2="76" y2="16" stroke="url(#av-ln)" strokeWidth="0.7"/>
                <line x1="76" y1="16" x2="80" y2="10" stroke="url(#av-ln)" strokeWidth="0.6" opacity="0.6"/>
                <line x1="80" y1="10" x2="85" y2="12" stroke="url(#av-ln)" strokeWidth="0.5" opacity="0.4"/>

                {/* Shoulder (bright) */}
                <circle cx="65" cy="42" r="2.8" fill="url(#av-sg)" opacity="0.85"/>
                <circle cx="65" cy="42" r="1.4" fill="white" opacity="0.95"/>
                {/* Head base */}
                <circle cx="72" cy="28" r="2.5" fill="url(#av-sg)" opacity="0.8"/>
                <circle cx="72" cy="28" r="1.2" fill="white" opacity="0.9"/>
                {/* Snout */}
                <circle cx="82" cy="22" r="2.2" fill="url(#av-sg)" opacity="0.75"/>
                <circle cx="82" cy="22" r="1.1" fill="white" opacity="0.85"/>
                {/* Eye */}
                <circle cx="76" cy="25" r="1" fill="white" opacity="0.8"/>
                {/* Ears */}
                <circle cx="68" cy="18" r="1.5" fill="url(#av-sg)" opacity="0.6"/>
                <circle cx="68" cy="18" r="0.7" fill="white" opacity="0.7"/>
                <circle cx="76" cy="16" r="1.5" fill="url(#av-sg)" opacity="0.6"/>
                <circle cx="76" cy="16" r="0.7" fill="white" opacity="0.7"/>
                {/* Horn */}
                <circle cx="80" cy="10" r="1.2" fill="url(#av-sg)" opacity="0.5"/>
                <circle cx="80" cy="10" r="0.6" fill="white" opacity="0.6"/>
                <circle cx="85" cy="12" r="1" fill="url(#av-sg)" opacity="0.35"/>
                <circle cx="85" cy="12" r="0.5" fill="white" opacity="0.45"/>
              </g>
            </g>
          </svg>

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
