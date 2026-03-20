/**
 * AutoLogin — Exchanges a demo token for a real session.
 *
 * URL: /auto-login?token=<jwt>
 *
 * Flow:
 * 1. Website links here with a signed demo token in the URL
 * 2. This page POSTs the token to /auth/demo-exchange
 * 3. Backend validates and returns access token + sets cookies
 * 4. Redirects to Decision Stream
 *
 * The URL contains a signed JWT (no password) that expires in 5 minutes.
 */

import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';

export default function AutoLogin() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [status, setStatus] = useState('Authenticating...');
  const [error, setError] = useState(null);

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setError('No demo token provided');
      return;
    }

    const exchange = async () => {
      try {
        setStatus('Verifying demo access...');
        const resp = await api.post('/auth/demo-exchange', { token });

        if (resp.data?.access_token) {
          // Store token for API calls
          localStorage.setItem('access_token', resp.data.access_token);

          setStatus('Welcome! Redirecting to Decision Stream...');

          // Refresh auth context to pick up the new user
          if (refreshUser) {
            await refreshUser();
          }

          // Redirect to Decision Stream after brief pause
          setTimeout(() => navigate('/', { replace: true }), 500);
        } else {
          setError('Authentication failed — no token returned');
        }
      } catch (err) {
        const msg = err.response?.data?.detail || err.message || 'Authentication failed';
        setError(msg);
      }
    };

    exchange();
  }, [searchParams, navigate, refreshUser]);

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
      color: 'white',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      <div style={{ textAlign: 'center', maxWidth: 400 }}>
        <img
          src="/Azirella_logo.png"
          alt="Azirella"
          style={{ height: 80, marginBottom: 24, opacity: 0.9 }}
          onError={(e) => { e.target.style.display = 'none'; }}
        />
        <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>
          Autonomy Platform
        </h1>
        {error ? (
          <div style={{ color: '#f87171', marginTop: 16 }}>
            <p style={{ fontSize: 16 }}>{error}</p>
            <a
              href="/login"
              style={{ color: '#93c5fd', marginTop: 12, display: 'inline-block' }}
            >
              Go to login →
            </a>
          </div>
        ) : (
          <div style={{ marginTop: 16 }}>
            <div style={{
              width: 32, height: 32, border: '3px solid rgba(255,255,255,0.3)',
              borderTopColor: 'white', borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
              margin: '0 auto 16px',
            }} />
            <p style={{ fontSize: 14, opacity: 0.8 }}>{status}</p>
          </div>
        )}
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}
