/**
 * useVoiceAssistant — "Hey Autonomy" wake word + voice I/O hook.
 *
 * States:
 *   PASSIVE  — continuous listening for wake word only (no audio leaves browser)
 *   WAKE     — wake word detected, chime plays, avatar activates (~1s)
 *   LISTENING — capturing user's full utterance
 *   PROCESSING — utterance sent to Azirella, waiting for response
 *   SPEAKING — TTS reading the response aloud
 *   IDLE     — voice assistant disabled
 *
 * Browser requirements: Chrome/Edge (Web Speech API), HTTPS or localhost.
 */

import { useState, useRef, useCallback, useEffect } from 'react';

// ── Constants ─────────────────────────────────────────────────────────────

const WAKE_WORDS = ['hey autonomy', 'hi autonomy', 'hey azirella', 'hi azirella', 'hey azerella', 'hi azerella', 'autonomy', 'azirella'];
const WAKE_CHIME_FREQ = 880; // A5 note
const SILENCE_TIMEOUT_MS = 3000; // Stop listening after 3s silence
const MAX_LISTEN_MS = 15000; // Max listening time per utterance

// ── State machine ─────────────────────────────────────────────────────────

export const VoiceState = {
  IDLE: 'idle',
  PASSIVE: 'passive',     // Listening for wake word only
  WAKE: 'wake',           // Wake word detected, transitioning
  LISTENING: 'listening', // Capturing user utterance
  PROCESSING: 'processing', // Waiting for LLM response
  SPEAKING: 'speaking',   // TTS reading response
};

// ── Wake word matching ────────────────────────────────────────────────────

function containsWakeWord(transcript) {
  const lower = transcript.toLowerCase().trim();
  return WAKE_WORDS.some(w => lower.includes(w));
}

function stripWakeWord(transcript) {
  let lower = transcript.toLowerCase().trim();
  for (const w of WAKE_WORDS) {
    const idx = lower.indexOf(w);
    if (idx !== -1) {
      // Return everything after the wake word
      const after = transcript.slice(idx + w.length).trim();
      return after || null;
    }
  }
  return transcript;
}

// ── Audio feedback ────────────────────────────────────────────────────────

function playWakeChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    // Two-tone chime: A5 then E6
    osc.type = 'sine';
    osc.frequency.setValueAtTime(WAKE_CHIME_FREQ, ctx.currentTime);
    osc.frequency.setValueAtTime(1318, ctx.currentTime + 0.12); // E6
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
  } catch {
    // Audio not available
  }
}

// ── TTS ───────────────────────────────────────────────────────────────────

function speak(text, onEnd) {
  if (!window.speechSynthesis || !text) {
    onEnd?.();
    return;
  }
  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  utterance.volume = 0.9;

  // Prefer a natural-sounding voice
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.find(v =>
    v.name.includes('Google') || v.name.includes('Samantha') ||
    v.name.includes('Microsoft') || v.name.includes('Natural')
  ) || voices.find(v => v.lang.startsWith('en'));
  if (preferred) utterance.voice = preferred;

  utterance.onend = () => onEnd?.();
  utterance.onerror = () => onEnd?.();

  window.speechSynthesis.speak(utterance);
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useVoiceAssistant({ onUtterance, enabled = false }) {
  const [state, setState] = useState(VoiceState.IDLE);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');

  const recognitionRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const maxListenTimerRef = useRef(null);
  const restartTimerRef = useRef(null);

  // ── Create SpeechRecognition instance ───────────────────────────────

  const createRecognition = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;

    return recognition;
  }, []);

  // ── Start passive listening (wake word detection) ───────────────────

  const startPassiveListening = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ok */ }
    }

    const recognition = createRecognition();
    if (!recognition) {
      console.warn('SpeechRecognition not available');
      setState(VoiceState.IDLE);
      return;
    }

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript;

        if (!result.isFinal) {
          // Check interim results for wake word
          if (containsWakeWord(text)) {
            recognition.stop();
            handleWakeWordDetected(text);
            return;
          }
        } else {
          // Final result — check for wake word
          if (containsWakeWord(text)) {
            recognition.stop();
            handleWakeWordDetected(text);
            return;
          }
        }
      }
    };

    recognition.onend = () => {
      // Restart passive listening (browsers stop after ~60s)
      if (state === VoiceState.PASSIVE) {
        restartTimerRef.current = setTimeout(() => {
          startPassiveListening();
        }, 200);
      }
    };

    recognition.onerror = (event) => {
      if (event.error === 'no-speech' || event.error === 'aborted') {
        // Normal — restart
        if (state === VoiceState.PASSIVE) {
          restartTimerRef.current = setTimeout(() => {
            startPassiveListening();
          }, 500);
        }
      } else {
        console.warn('Speech recognition error:', event.error);
      }
    };

    recognitionRef.current = recognition;
    setState(VoiceState.PASSIVE);

    try {
      recognition.start();
    } catch (e) {
      console.warn('Failed to start speech recognition:', e);
    }
  }, [createRecognition]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handle wake word detection ──────────────────────────────────────

  const handleWakeWordDetected = useCallback((wakeTranscript) => {
    playWakeChime();
    setState(VoiceState.WAKE);

    // Check if the user said something after the wake word
    const afterWake = stripWakeWord(wakeTranscript);

    // Brief pause for the chime, then start active listening
    setTimeout(() => {
      if (afterWake && afterWake.length > 3) {
        // User already said their query inline: "Hey Autonomy, show me inventory"
        handleUtteranceComplete(afterWake);
      } else {
        startActiveListening();
      }
    }, 400);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Start active listening (capture full utterance) ─────────────────

  const startActiveListening = useCallback(() => {
    const recognition = createRecognition();
    if (!recognition) return;

    let finalText = '';

    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript + ' ';
          setTranscript(finalText.trim());
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      setInterimTranscript(interim);

      // Reset silence timer on any speech
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = setTimeout(() => {
        // Silence detected — stop listening
        recognition.stop();
      }, SILENCE_TIMEOUT_MS);
    };

    recognition.onend = () => {
      clearTimeout(silenceTimerRef.current);
      clearTimeout(maxListenTimerRef.current);
      if (finalText.trim()) {
        handleUtteranceComplete(finalText.trim());
      } else {
        // No speech captured — go back to passive
        startPassiveListening();
      }
    };

    recognition.onerror = (event) => {
      clearTimeout(silenceTimerRef.current);
      clearTimeout(maxListenTimerRef.current);
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.warn('Active listening error:', event.error);
      }
      startPassiveListening();
    };

    recognitionRef.current = recognition;
    setState(VoiceState.LISTENING);
    setTranscript('');
    setInterimTranscript('');

    try {
      recognition.start();
    } catch (e) {
      console.warn('Failed to start active listening:', e);
      startPassiveListening();
    }

    // Safety: max listen time
    maxListenTimerRef.current = setTimeout(() => {
      try { recognition.stop(); } catch { /* ok */ }
    }, MAX_LISTEN_MS);
  }, [createRecognition, startPassiveListening]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handle completed utterance ──────────────────────────────────────

  const handleUtteranceComplete = useCallback((text) => {
    setState(VoiceState.PROCESSING);
    setTranscript(text);
    setInterimTranscript('');

    // Send to Azirella via callback
    onUtterance?.(text);
  }, [onUtterance]);

  // ── Speak response (TTS) ────────────────────────────────────────────

  const speakResponse = useCallback((text) => {
    setState(VoiceState.SPEAKING);
    speak(text, () => {
      // After speaking, return to passive listening
      setState(VoiceState.PASSIVE);
      startPassiveListening();
    });
  }, [startPassiveListening]);

  // ── Stop speaking ───────────────────────────────────────────────────

  const stopSpeaking = useCallback(() => {
    window.speechSynthesis?.cancel();
    setState(VoiceState.PASSIVE);
    startPassiveListening();
  }, [startPassiveListening]);

  // ── Enable/disable ──────────────────────────────────────────────────

  useEffect(() => {
    if (enabled) {
      startPassiveListening();
    } else {
      setState(VoiceState.IDLE);
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch { /* ok */ }
      }
      clearTimeout(silenceTimerRef.current);
      clearTimeout(maxListenTimerRef.current);
      clearTimeout(restartTimerRef.current);
      window.speechSynthesis?.cancel();
    }

    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch { /* ok */ }
      }
      clearTimeout(silenceTimerRef.current);
      clearTimeout(maxListenTimerRef.current);
      clearTimeout(restartTimerRef.current);
      window.speechSynthesis?.cancel();
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load voices early
  useEffect(() => {
    window.speechSynthesis?.getVoices();
  }, []);

  return {
    state,
    transcript,
    interimTranscript,
    speakResponse,
    stopSpeaking,
    isAvailable: !!(window.SpeechRecognition || window.webkitSpeechRecognition),
  };
}

export default useVoiceAssistant;
