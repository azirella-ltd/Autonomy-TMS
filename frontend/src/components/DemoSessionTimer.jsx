import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";

/**
 * DemoSessionTimer — Polls /api/v1/auth/demo-session-check every 60s.
 * When the 30-min demo session expires, shows a modal informing the user
 * they can return in 1 hour, then logs them out.
 */
export default function DemoSessionTimer() {
  const { user, logout } = useAuth();
  const [showExpiredModal, setShowExpiredModal] = useState(false);
  const [remaining, setRemaining] = useState(null);
  const [cooldownMinutes, setCooldownMinutes] = useState(60);
  const [canRejoinAt, setCanRejoinAt] = useState(null);

  const checkSession = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/auth/demo-session-check", {
        credentials: "include",
      });
      if (!res.ok) return;
      const data = await res.json();
      if (!data.demo_user) return;

      if (data.expired) {
        setCooldownMinutes(data.cooldown_minutes || 60);
        setCanRejoinAt(data.can_rejoin_at);
        setShowExpiredModal(true);
      } else {
        setRemaining(data.remaining_minutes);
      }
    } catch {
      // Silently ignore — don't block the demo if the check fails
    }
  }, []);

  useEffect(() => {
    // Only poll for demo users
    if (!user) return;

    // Initial check
    checkSession();

    // Poll every 60 seconds
    const interval = setInterval(checkSession, 60000);
    return () => clearInterval(interval);
  }, [user, checkSession]);

  const handleClose = useCallback(() => {
    setShowExpiredModal(false);
    if (logout) logout();
  }, [logout]);

  // Show a subtle remaining-time badge in the last 5 minutes
  const showWarning = remaining !== null && remaining <= 5 && !showExpiredModal;

  return (
    <>
      {/* Last 5 minutes warning badge */}
      {showWarning && (
        <div
          style={{
            position: "fixed",
            top: 12,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 9998,
            background: "rgba(251, 191, 36, 0.15)",
            border: "1px solid rgba(251, 191, 36, 0.4)",
            borderRadius: 8,
            padding: "6px 16px",
            fontSize: 13,
            color: "#fbbf24",
            fontWeight: 500,
            backdropFilter: "blur(8px)",
          }}
        >
          Demo session ends in ~{remaining} min
        </div>
      )}

      {/* Expired modal */}
      {showExpiredModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.7)",
            backdropFilter: "blur(4px)",
          }}
        >
          <div
            style={{
              background: "linear-gradient(135deg, #1a1035, #0d1f3c)",
              border: "1px solid rgba(124, 58, 237, 0.3)",
              borderRadius: 16,
              padding: "40px 36px",
              maxWidth: 440,
              textAlign: "center",
              color: "#e2e8f0",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            <div style={{ fontSize: 36, marginBottom: 16 }}>⏰</div>
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                marginBottom: 12,
                background: "linear-gradient(135deg, #a78bfa, #7c3aed)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Demo Session Complete
            </h2>
            <p style={{ fontSize: 15, color: "#cbd5e1", marginBottom: 8 }}>
              Your 30-minute demo session has ended. Thank you for exploring the
              Autonomy platform!
            </p>
            <p style={{ fontSize: 14, color: "#94a3b8", marginBottom: 24 }}>
              You can log in again in{" "}
              <strong style={{ color: "#fbbf24" }}>
                {cooldownMinutes} minutes
              </strong>
              {canRejoinAt && (
                <span>
                  {" "}
                  (at{" "}
                  {new Date(canRejoinAt).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  )
                </span>
              )}
              .
            </p>
            <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
              <a
                href="https://azirella.com/contact"
                style={{
                  padding: "10px 24px",
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.15)",
                  borderRadius: 8,
                  color: "#e2e8f0",
                  textDecoration: "none",
                  fontSize: 14,
                  fontWeight: 500,
                }}
              >
                Request Full Demo
              </a>
              <button
                onClick={handleClose}
                style={{
                  padding: "10px 24px",
                  background: "linear-gradient(135deg, #7c3aed, #6d28d9)",
                  border: "none",
                  borderRadius: 8,
                  color: "white",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
