import React, { useState, useEffect } from 'react'
import Joyride, { STATUS, ACTIONS, EVENTS } from 'react-joyride'

const Tutorial = ({ runTutorial, onComplete }) => {
  const [run, setRun] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    if (runTutorial) {
      setRun(true)
    }
  }, [runTutorial])

  const steps = [
    {
      target: 'body',
      content: (
        <div>
          <h2 className="text-xl font-bold mb-2">Welcome to Autonomy!</h2>
          <p>
            This interactive tutorial will guide you through the key features of the game.
            You can skip this tutorial at any time or restart it from the help menu.
          </p>
        </div>
      ),
      placement: 'center',
      disableBeacon: true,
    },
    {
      target: '.game-board',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Your Game Board</h3>
          <p>
            This is your main game interface. Here you'll see your current inventory,
            backlog, incoming orders, and shipments. Keep an eye on these metrics
            to make informed ordering decisions.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: '.inventory-display',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Inventory & Backlog</h3>
          <p>
            Your <strong>inventory</strong> shows items in stock. Too much inventory
            costs money to hold. <strong>Backlog</strong> represents unfulfilled orders,
            which also incur costs and hurt service levels.
          </p>
        </div>
      ),
      placement: 'left',
    },
    {
      target: '.order-input',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Place Your Orders</h3>
          <p>
            Each round, enter your order quantity here. Your goal is to balance
            inventory costs with service levels. Order too little and you'll have
            backlog. Order too much and you'll have excess inventory costs.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: '[data-tutorial="ai-suggestion"]',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">AI Suggestions 🤖</h3>
          <p>
            Click here to get AI-powered order recommendations based on demand
            patterns, inventory levels, and supply chain dynamics. The AI analyzes
            historical data to help you make better decisions.
          </p>
        </div>
      ),
      placement: 'left',
    },
    {
      target: '[data-tutorial="analytics-tab"]',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Analytics Dashboard 📊</h3>
          <p>
            View detailed analytics including demand patterns, the bullwhip effect,
            cost breakdowns, and performance metrics. Use these insights to
            understand supply chain dynamics.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: '[data-tutorial="negotiations-tab"]',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Negotiate with Partners 🤝</h3>
          <p>
            Collaborate with other users in the supply chain. Propose negotiations
            to adjust order quantities, share information, or coordinate strategies
            for better overall performance.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: '[data-tutorial="visibility-tab"]',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Visibility Sharing 👁️</h3>
          <p>
            Share your inventory and demand data with supply chain partners.
            Greater visibility helps reduce the bullwhip effect and improves
            coordination across the entire supply chain.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: '[data-tutorial="achievements-tab"]',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Achievements & Progression 🏆</h3>
          <p>
            Track your achievements, earn points, and level up as you play.
            Complete challenges to unlock badges and compete on leaderboards
            with other users.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: '[data-tutorial="reports-tab"]',
      content: (
        <div>
          <h3 className="text-lg font-bold mb-2">Game Reports 📈</h3>
          <p>
            Generate comprehensive game reports with insights, recommendations,
            and performance analysis. Export your data in CSV, JSON, or Excel
            format for further analysis.
          </p>
        </div>
      ),
      placement: 'bottom',
    },
    {
      target: 'body',
      content: (
        <div>
          <h2 className="text-xl font-bold mb-2">You're Ready to Play! 🎉</h2>
          <p className="mb-3">
            Remember: The goal is to minimize total supply chain costs while
            maintaining high service levels. Key strategies include:
          </p>
          <ul className="list-disc list-inside space-y-1 mb-3">
            <li>Maintain stable order patterns to reduce the bullwhip effect</li>
            <li>Use AI suggestions and analytics to inform decisions</li>
            <li>Collaborate with supply chain partners through negotiations</li>
            <li>Share visibility to improve coordination</li>
            <li>Monitor your performance and learn from insights</li>
          </ul>
          <p className="text-sm text-gray-600">
            You can restart this tutorial anytime from the Help menu.
          </p>
        </div>
      ),
      placement: 'center',
    },
  ]

  const handleJoyrideCallback = (data) => {
    const { status, type, action, index } = data

    if ([EVENTS.STEP_AFTER, EVENTS.TARGET_NOT_FOUND].includes(type)) {
      // Update state to advance or retreat the tour
      setStepIndex(index + (action === ACTIONS.PREV ? -1 : 1))
    } else if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      // Reset tour state
      setRun(false)
      setStepIndex(0)

      // Call completion callback
      if (onComplete) {
        onComplete(status === STATUS.FINISHED)
      }
    }
  }

  return (
    <Joyride
      steps={steps}
      run={run}
      stepIndex={stepIndex}
      continuous
      showProgress
      showSkipButton
      scrollToFirstStep
      disableScrolling={false}
      callback={handleJoyrideCallback}
      styles={{
        options: {
          primaryColor: '#4f46e5',
          textColor: '#1f2937',
          backgroundColor: '#ffffff',
          arrowColor: '#ffffff',
          overlayColor: 'rgba(0, 0, 0, 0.5)',
          zIndex: 10000,
        },
        tooltip: {
          borderRadius: 8,
          fontSize: 14,
        },
        tooltipContainer: {
          textAlign: 'left',
        },
        buttonNext: {
          backgroundColor: '#4f46e5',
          borderRadius: 6,
          padding: '8px 16px',
          fontSize: 14,
          fontWeight: 500,
        },
        buttonBack: {
          color: '#6b7280',
          marginRight: 8,
        },
        buttonSkip: {
          color: '#6b7280',
        },
      }}
      locale={{
        back: 'Back',
        close: 'Close',
        last: 'Finish',
        next: 'Next',
        skip: 'Skip Tutorial',
      }}
    />
  )
}

export default Tutorial
