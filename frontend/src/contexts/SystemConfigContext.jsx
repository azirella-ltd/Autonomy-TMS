import React, { createContext, useContext, useEffect, useState } from 'react';
import simulationApi from '../services/api';

const SystemConfigContext = createContext({ ranges: {}, refresh: async () => {}, save: async () => {} });

export function SystemConfigProvider({ children }) {
  const [ranges, setRanges] = useState({});
  const refresh = async () => {
    try {
      const data = await simulationApi.getSystemConfig();
      setRanges(data || {});
    } catch (e) {
      const raw = localStorage.getItem('systemConfigRanges');
      if (raw) {
        try { setRanges(JSON.parse(raw)); } catch {}
      }
    }
  };
  const save = async (cfg) => {
    await simulationApi.saveSystemConfig(cfg);
    setRanges(cfg);
  };
  useEffect(() => { refresh(); }, []);
  return (
    <SystemConfigContext.Provider value={{ ranges, refresh, save }}>
      {children}
    </SystemConfigContext.Provider>
  );
}

export function useSystemConfig() {
  return useContext(SystemConfigContext);
}

