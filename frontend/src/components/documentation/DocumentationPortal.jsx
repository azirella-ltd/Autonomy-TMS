/**
 * Documentation Portal Component
 * Phase 6 Sprint 4: User Experience Enhancements
 *
 * In-app documentation viewer with search and navigation.
 * Features:
 * - Table of contents
 * - Search functionality
 * - Code examples
 * - Context-sensitive help
 */

import { useState } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Input,
} from '../common';
import {
  Search,
  ChevronDown,
  ChevronRight,
  Home,
  FileText,
  Code,
  Video,
} from 'lucide-react';

const DOCUMENTATION_STRUCTURE = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: <Home className="h-4 w-4" />,
    children: [
      { id: 'intro', title: 'Introduction' },
      { id: 'quick-start', title: 'Quick Start Guide' },
      { id: 'concepts', title: 'Core Concepts' }
    ]
  },
  {
    id: 'supply-chain',
    title: 'Supply Chain Configuration',
    icon: <FileText className="h-4 w-4" />,
    children: [
      { id: 'sc-overview', title: 'Overview' },
      { id: 'sc-sites', title: 'Sites & Lanes' },
      { id: 'sc-items', title: 'Items & BOMs' },
      { id: 'sc-dag', title: 'DAG Topology' }
    ]
  },
  {
    id: 'agents',
    title: 'AI Agents',
    icon: <Code className="h-4 w-4" />,
    children: [
      { id: 'agent-types', title: 'Agent Types' },
      { id: 'agent-config', title: 'Configuration' },
      { id: 'llm-agents', title: 'LLM Agents' },
      { id: 'gnn-training', title: 'Network Agent Training' }
    ]
  },
  {
    id: 'analytics',
    title: 'Analytics & Reporting',
    icon: <FileText className="h-4 w-4" />,
    children: [
      { id: 'metrics', title: 'Metrics' },
      { id: 'bullwhip', title: 'Bullwhip Effect' },
      { id: 'monte-carlo', title: 'Monte Carlo Simulation' },
      { id: 'stochastic', title: 'Stochastic Analysis' }
    ]
  },
  {
    id: 'tutorials',
    title: 'Video Tutorials',
    icon: <Video className="h-4 w-4" />,
    children: [
      { id: 'video-intro', title: 'Introduction (5min)' },
      { id: 'video-setup', title: 'Scenario Setup (10min)' },
      { id: 'video-analytics', title: 'Analytics Dashboard (8min)' }
    ]
  }
];

const DOCUMENTATION_CONTENT = {
  intro: {
    title: 'Introduction to Autonomy',
    content: `
# Welcome to Autonomy

Autonomy is a comprehensive supply chain platform designed to demonstrate the **bullwhip effect** and teach supply chain management principles through gamification.

## What is the Bullwhip Effect?

The bullwhip effect is a phenomenon where small fluctuations in demand at the retail level cause progressively larger fluctuations upstream in the supply chain.

## Key Features

- **Multi-echelon supply chains**: Model complex networks with multiple tiers
- **AI-powered agents**: Intelligent agents using ML, LLM, and heuristic strategies
- **Real-time analytics**: Monitor performance with comprehensive metrics
- **Stochastic modeling**: Analyze uncertainty with Monte Carlo simulations
- **Flexible configurations**: DAG-based network topologies

## Getting Started

1. Create a new game or use a template
2. Configure your supply chain network
3. Assign scenarioUsers or AI agents
4. Run simulations and analyze results
    `,
    tags: ['basics', 'overview'],
    lastUpdated: '2026-01-14'
  },
  'quick-start': {
    title: 'Quick Start Guide',
    content: `
# Quick Start Guide

Get up and running in 5 minutes with our Quick Start Wizard.

## Step 1: Launch Quick Start Wizard

Navigate to **Create New Scenario** and select **Quick Start Wizard**.

## Step 2: Choose Your Industry

Select an industry vertical:
- **Retail**: Consumer goods distribution
- **Manufacturing**: Production and assembly
- **Logistics**: Transportation networks
- **Healthcare**: Medical supplies

## Step 3: Select Difficulty

- **Beginner**: Simple, predictable patterns
- **Intermediate**: Moderate complexity
- **Advanced**: Complex scenarios
- **Expert**: Maximum challenge

## Step 4: Configure & Launch

- Set number of scenarioUsers (1-10)
- Enable optional features (Monte Carlo, AI agents)
- Review template and launch

## Example Configuration

\`\`\`json
{
  "industry": "retail",
  "difficulty": "beginner",
  "num_scenario_users": 4,
  "features": ["ai_agents"]
}
\`\`\`
    `,
    tags: ['tutorial', 'beginner'],
    lastUpdated: '2026-01-14'
  },
  concepts: {
    title: 'Core Concepts',
    content: `
# Core Concepts

Understanding key concepts is essential for effective supply chain management.

## Supply Chain Network

A **supply chain network** consists of:

### Sites
- **Market Supply**: Upstream sources (infinite supply)
- **Market Demand**: Terminal demand sinks
- **Inventory**: Storage and fulfillment sites
- **Manufacturer**: Transform sites with BOMs

### Lanes
Directed connections between sites representing material flow.

### Items
Products that flow through the network. Each item can have:
- **BOM**: Bill of materials for transformation
- **Lead time**: Shipping delays
- **Cost**: Inventory holding and ordering costs

## Simulation Mechanics

### Order Cycle
1. **Receive shipments** from upstream
2. **Fulfill demand** from downstream
3. **Calculate backlog** for unfulfilled orders
4. **Place order** to upstream supplier

### Performance Metrics
- **Total cost**: Holding + ordering + backlog costs
- **Service level**: Orders fulfilled on time
- **Bullwhip ratio**: Demand variability amplification
- **Inventory turnover**: Efficiency metric

## Agent Strategies

Different strategies for decision-making:
- **Naive**: Mirror incoming demand
- **Conservative**: Maintain stable orders
- **Bullwhip**: Intentionally amplify variability
- **ML Forecast**: Machine learning predictions
- **LLM**: OpenAI-powered reasoning
    `,
    tags: ['concepts', 'fundamentals'],
    lastUpdated: '2026-01-14'
  }
};

const DocumentationPortal = ({ initialDoc }) => {
  const [openSections, setOpenSections] = useState(['getting-started']);
  const [selectedDoc, setSelectedDoc] = useState(initialDoc || 'intro');
  const [searchQuery, setSearchQuery] = useState('');

  const toggleSection = (sectionId) => {
    setOpenSections((prev) =>
      prev.includes(sectionId)
        ? prev.filter((id) => id !== sectionId)
        : [...prev, sectionId]
    );
  };

  const handleDocClick = (docId) => {
    setSelectedDoc(docId);
  };

  const renderContent = () => {
    const doc = DOCUMENTATION_CONTENT[selectedDoc];
    if (!doc) {
      return (
        <Alert>
          <AlertDescription>Documentation content coming soon.</AlertDescription>
        </Alert>
      );
    }

    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">{doc.title}</h1>

        {doc.tags && (
          <div className="flex gap-1 mb-4">
            {doc.tags.map((tag) => (
              <Badge key={tag} variant="secondary">{tag}</Badge>
            ))}
          </div>
        )}

        <hr className="my-4" />

        <div className="prose prose-sm max-w-none">
          {doc.content.split('\n').map((line, index) => {
            if (line.startsWith('# ')) {
              return (
                <h1 key={index} className="text-2xl font-bold mt-6 mb-4">
                  {line.substring(2)}
                </h1>
              );
            } else if (line.startsWith('## ')) {
              return (
                <h2 key={index} className="text-xl font-semibold mt-4 mb-2">
                  {line.substring(3)}
                </h2>
              );
            } else if (line.startsWith('### ')) {
              return (
                <h3 key={index} className="text-lg font-medium mt-4 mb-2">
                  {line.substring(4)}
                </h3>
              );
            } else if (line.startsWith('```')) {
              return null; // Handle code blocks separately
            } else if (line.trim().startsWith('-')) {
              return (
                <li key={index} className="ml-4 text-sm">
                  {line.trim().substring(2)}
                </li>
              );
            } else if (line.trim()) {
              return (
                <p key={index} className="mb-2">
                  {line}
                </p>
              );
            }
            return <br key={index} />;
          })}
        </div>

        {doc.lastUpdated && (
          <div className="mt-8 pt-4 border-t">
            <p className="text-xs text-muted-foreground">
              Last updated: {doc.lastUpdated}
            </p>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-[calc(100vh-200px)]">
      {/* Sidebar */}
      <div className="w-72 flex-shrink-0 border-r overflow-y-auto">
        <div className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search docs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <nav className="px-2">
          {DOCUMENTATION_STRUCTURE.map((section) => (
            <div key={section.id} className="mb-1">
              <button
                onClick={() => toggleSection(section.id)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md hover:bg-muted transition-colors"
              >
                {section.icon}
                <span className="flex-1 text-left font-medium">{section.title}</span>
                {openSections.includes(section.id) ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </button>
              {openSections.includes(section.id) && (
                <div className="ml-6 mt-1">
                  {section.children.map((child) => (
                    <button
                      key={child.id}
                      onClick={() => handleDocClick(child.id)}
                      className={`w-full text-left px-3 py-1.5 text-sm rounded-md transition-colors ${
                        selectedDoc === child.id
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'hover:bg-muted'
                      }`}
                    >
                      {child.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div className="flex-1 p-6 overflow-y-auto">
        <nav className="flex items-center gap-2 text-sm mb-6">
          <button
            onClick={() => handleDocClick('intro')}
            className="text-muted-foreground hover:text-foreground"
          >
            Documentation
          </button>
          <span className="text-muted-foreground">/</span>
          <span className="text-foreground">
            {DOCUMENTATION_CONTENT[selectedDoc]?.title || 'Unknown'}
          </span>
        </nav>

        {renderContent()}
      </div>
    </div>
  );
};

export default DocumentationPortal;
