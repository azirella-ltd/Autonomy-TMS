import { createContext, useContext, useState } from 'react';

const HelpContext = createContext();

export const HelpProvider = ({ children }) => {
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [activeHelpTab, setActiveHelpTab] = useState('getting-started');
  const [showTutorial, setShowTutorial] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(() => {
    // Check if user has completed onboarding
    if (typeof window !== 'undefined') {
      return localStorage.getItem('hasCompletedOnboarding') !== 'true';
    }
    return false;
  });

  const openHelp = (tab = 'getting-started') => {
    setActiveHelpTab(tab);
    setIsHelpOpen(true);
  };

  const closeHelp = () => {
    setIsHelpOpen(false);
  };

  const openTutorial = (options = {}) => {
    setShowTutorial(true);
    setIsHelpOpen(false);
    if (options.showOnboarding !== undefined) {
      setShowOnboarding(options.showOnboarding);
    }
  };

  const closeTutorial = () => {
    setShowTutorial(false);
    if (showOnboarding) {
      setShowOnboarding(false);
      if (typeof window !== 'undefined') {
        localStorage.setItem('hasCompletedOnboarding', 'true');
      }
    }
  };

  return (
    <HelpContext.Provider
      value={{
        isHelpOpen,
        activeHelpTab,
        showTutorial,
        showOnboarding,
        openHelp,
        closeHelp,
        openTutorial,
        closeTutorial,
        setActiveHelpTab,
      }}
    >
      {children}
    </HelpContext.Provider>
  );
};

export const useHelp = () => {
  const context = useContext(HelpContext);
  if (context === undefined) {
    throw new Error('useHelp must be used within a HelpProvider');
  }
  return context;
};

export default HelpContext;
