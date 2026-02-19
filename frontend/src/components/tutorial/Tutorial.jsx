import { useState, useEffect, useCallback } from 'react';
import { XMarkIcon, ArrowRightIcon, ArrowLeftIcon, PlayIcon } from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router-dom';

const Tutorial = ({ onClose, showOnboarding = false }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const navigate = useNavigate();

  const steps = [
    {
      title: 'Welcome to Autonomy',
      content: 'Autonomy is a supply chain platform that demonstrates the challenges of supply chain management. You\'ll take on the role of a supply chain manager and make decisions to optimize your inventory and meet customer demand.',
      image: '/images/tutorial/welcome.svg',
      showNext: true,
      showPrev: false,
      showSkip: true,
    },
    {
      title: 'Game Objective',
      content: 'Your goal is to minimize costs while meeting customer demand. You\'ll need to balance inventory levels, backorders, and ordering to achieve the best possible score.',
      image: '/images/tutorial/objective.svg',
      showNext: true,
      showPrev: true,
      showSkip: true,
    },
    {
      title: 'The Supply Chain',
      content: 'The game simulates a four-stage supply chain: Retailer, Wholesaler, Distributor, and Manufacturer. You can play as any of these roles, each with its own challenges and strategies.',
      image: '/images/tutorial/supply-chain.svg',
      showNext: true,
      showPrev: true,
      showSkip: true,
    },
    {
      title: 'Making Orders',
      content: 'Each turn, you\'ll need to decide how many units to order from your upstream partner. Consider your current inventory, incoming orders, and customer demand when making your decision.',
      image: '/images/tutorial/orders.svg',
      showNext: true,
      showPrev: true,
      showSkip: true,
    },
    {
      title: 'Costs & Scoring',
      content: 'You\'re scored based on your performance. Points are awarded for meeting demand and maintaining optimal inventory levels, while backorders and excess inventory result in penalties.',
      image: '/images/tutorial/scoring.svg',
      showNext: true,
      showPrev: true,
      showSkip: true,
    },
    {
      title: 'Ready to Play?',
      content: 'Now that you understand the basics, you\'re ready to start playing! You can always access this tutorial again from the help menu.',
      image: '/images/tutorial/ready.svg',
      showNext: false,
      showPrev: true,
      showSkip: false,
      showFinish: true,
    },
  ];

  const currentStepData = steps[currentStep];

  const handleFinish = useCallback(() => {
    if (showOnboarding) {
      localStorage.setItem('hasCompletedOnboarding', 'true');
      navigate('/lobby');
    }
    onClose();
  }, [navigate, onClose, showOnboarding]);

  const handleNext = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleFinish();
    }
  }, [currentStep, steps.length, handleFinish]);

  const handlePrev = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  }, [currentStep]);

  const handleSkip = () => {
    if (showOnboarding) {
      localStorage.setItem('hasCompletedOnboarding', 'true');
    }
    onClose();
  };

  

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowRight') {
        handleNext();
      } else if (e.key === 'ArrowLeft') {
        handlePrev();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStep, onClose, handleNext, handlePrev]);

  // Progress dots
  const ProgressDots = () => (
    <div className="flex justify-center mt-6 space-x-2">
      {steps.map((_, index) => (
        <button
          key={index}
          onClick={() => setCurrentStep(index)}
          className={`h-3 w-3 rounded-full transition-colors ${index === currentStep ? 'bg-indigo-600' : 'bg-gray-300'}`}
          aria-label={`Go to step ${index + 1}`}
        />
      ))}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
      <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" aria-hidden="true" onClick={onClose}></div>
        
        <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
        
        <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full sm:p-6">
          <div className="absolute top-0 right-0 pt-4 pr-4">
            <button
              type="button"
              className="bg-white rounded-md text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              onClick={onClose}
            >
              <span className="sr-only">Close</span>
              <XMarkIcon className="h-6 w-6" aria-hidden="true" />
            </button>
          </div>
          
          <div className="sm:flex sm:items-start">
            <div className="mt-3 text-center sm:mt-0 sm:text-left w-full">
              <h3 className="text-2xl leading-6 font-bold text-gray-900 mb-6" id="modal-title">
                {currentStepData.title}
              </h3>
              
              <div className="mt-2">
                <div className="bg-gray-50 rounded-lg p-6 mb-6 flex justify-center">
                  {currentStepData.image ? (
                    <img 
                      src={currentStepData.image} 
                      alt={currentStepData.title} 
                      className="h-48 w-full object-contain"
                      onError={(e) => {
                        // Fallback to a placeholder if the image fails to load
                        e.target.onerror = null;
                        e.target.src = `https://via.placeholder.com/400x200?text=${encodeURIComponent(currentStepData.title)}`;
                      }}
                    />
                  ) : (
                    <div className="h-48 w-full flex items-center justify-center bg-gray-100 rounded">
                      <span className="text-gray-400">Illustration</span>
                    </div>
                  )}
                </div>
                
                <p className="text-gray-700 mb-6">
                  {currentStepData.content}
                </p>
                
                {currentStep === 0 && (
                  <div className="bg-indigo-50 p-4 rounded-lg mb-6">
                    <h4 className="font-medium text-indigo-800 mb-2">Quick Tips</h4>
                    <ul className="list-disc list-inside text-sm text-indigo-700 space-y-1">
                      <li>Use the arrow keys to navigate through the tutorial</li>
                      <li>Click on the dots below to jump to a specific section</li>
                      <li>You can always access this tutorial from the help menu</li>
                    </ul>
                  </div>
                )}
                
                <ProgressDots />
                
                <div className="mt-6 flex justify-between">
                  <div>
                    {currentStepData.showPrev && (
                      <button
                        type="button"
                        onClick={handlePrev}
                        className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                      >
                        <ArrowLeftIcon className="-ml-1 mr-2 h-5 w-5" aria-hidden="true" />
                        Back
                      </button>
                    )}
                  </div>
                  
                  <div className="flex space-x-3">
                    {currentStepData.showSkip && (
                      <button
                        type="button"
                        onClick={handleSkip}
                        className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
                      >
                        Skip Tutorial
                      </button>
                    )}
                    
                    {currentStepData.showNext ? (
                      <button
                        type="button"
                        onClick={handleNext}
                        className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                      >
                        Next
                        <ArrowRightIcon className="ml-2 -mr-1 h-5 w-5" aria-hidden="true" />
                      </button>
                    ) : currentStepData.showFinish ? (
                      <button
                        type="button"
                        onClick={handleFinish}
                        className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                      >
                        Get Started
                        <PlayIcon className="ml-2 -mr-1 h-5 w-5" aria-hidden="true" />
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Tutorial;
