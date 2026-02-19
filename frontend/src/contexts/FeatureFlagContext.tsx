/**
 * FeatureFlagContext - Feature flag management
 */

import React, { createContext, useContext, useState, ReactNode } from 'react';

interface FeatureFlags {
  agentReportEnabled?: boolean;
  v4ReportEnabled?: boolean;
  [key: string]: boolean | undefined;
}

interface FeatureFlagContextType {
  flags: FeatureFlags;
  setFlag: (key: string, value: boolean) => void;
  isEnabled: (key: string) => boolean;
  isFeatureEnabled: (key: string) => boolean;
}

const FeatureFlagContext = createContext<FeatureFlagContextType | undefined>(undefined);

interface FeatureFlagProviderProps {
  children: ReactNode;
  initialFlags?: FeatureFlags;
}

export const FeatureFlagProvider: React.FC<FeatureFlagProviderProps> = ({
  children,
  initialFlags = {}
}) => {
  const [flags, setFlags] = useState<FeatureFlags>(initialFlags);

  const setFlag = (key: string, value: boolean) => {
    setFlags(prev => ({ ...prev, [key]: value }));
  };

  const isEnabled = (key: string) => {
    return flags[key] ?? false;
  };

  return (
    <FeatureFlagContext.Provider value={{ flags, setFlag, isEnabled, isFeatureEnabled: isEnabled }}>
      {children}
    </FeatureFlagContext.Provider>
  );
};

export const useFeatureFlags = (): FeatureFlagContextType => {
  const context = useContext(FeatureFlagContext);
  if (context === undefined) {
    // Return a default context if not wrapped in provider
    return {
      flags: {},
      setFlag: () => {},
      isEnabled: () => false,
      isFeatureEnabled: () => false,
    };
  }
  return context;
};

export default FeatureFlagContext;
