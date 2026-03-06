// /frontend/src/index.js
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { SystemConfigProvider } from "./contexts/SystemConfigContext.jsx";
import { HelpProvider } from "./contexts/HelpContext.jsx";
import "./index.css";
import "leaflet/dist/leaflet.css";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { ActiveConfigProvider } from "./contexts/ActiveConfigContext";
import simulationApi, { api as http } from "./services/api";
import { API_BASE_URL } from "./config/api.ts";
import { SnackbarProvider } from "notistack";

async function probe(base, path = "/health") {
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}${path}`, { credentials: "include" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return true;
  } catch (_) {
    return false;
  }
}

async function detectApiBase() {
  const candidates = [
    API_BASE_URL,
    "/api/v1",
    "http://localhost:8000/api/v1",
  ].filter(Boolean);

  for (const c of candidates) {
    const ok = await probe(c, "/health");
    if (ok) return c;
  }
  // All candidates failed — fall back to the configured base URL rather than
  // trying a non-versioned path like "/api" which would cause 404s on every
  // subsequent request.
  console.warn("No healthy API base detected, using configured base:", API_BASE_URL);
  return API_BASE_URL;
}

async function init() {
  try {
    const resolvedBase = await detectApiBase();
    http.defaults.baseURL = resolvedBase;
    console.log("API base resolved:", resolvedBase);
    const data = await simulationApi.health();
    console.log("API health:", data);
    return true;
  } catch (err) {
    const status = err?.response?.status;
    const text = err?.response?.statusText || err?.message;
    const payload = err?.response?.data;
    console.error("API connection test failed:", { status, text, payload, envBase: API_BASE_URL, resolvedBase: http?.defaults?.baseURL });
    throw new Error(`API connection failed: ${text || "Unknown"}`);
  }
}

init()
  .then(() => {
    const root = ReactDOM.createRoot(document.getElementById("root"));
    root.render(
      <HelmetProvider>
        <BrowserRouter>
          <AuthProvider>
            <ActiveConfigProvider>
            <SystemConfigProvider>
              <HelpProvider>
                <SnackbarProvider
                  maxSnack={3}
                  anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
                >
                  <App />
                </SnackbarProvider>
              </HelpProvider>
            </SystemConfigProvider>
            </ActiveConfigProvider>
          </AuthProvider>
        </BrowserRouter>
      </HelmetProvider>
    );
  })
  .catch((e) => {
    const el = document.getElementById("root");
    el.innerHTML = `
      <div style="font-family: 'Trebuchet MS', 'TrebuchetMS', 'Lucida Sans Unicode', 'Lucida Grande', sans-serif; padding: 32px;">
        <h1 style="margin:0 0 8px 0;">Error</h1>
        <p style="margin:0 0 16px 0;">Initialization failed: ${e.message}</p>
        <p style="color:#666;margin:0;">Current Step:<br/><strong>Initializing...</strong></p>
        <p style="margin-top:16px;color:#888;">Tip: backend should be reachable at /api, /api/v1, or http://localhost:8000/api/v1</p>
      </div>`;
  });
