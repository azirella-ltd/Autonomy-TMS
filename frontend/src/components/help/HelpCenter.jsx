import React, { useState, useMemo } from 'react'
import {
  MagnifyingGlassIcon,
  BookOpenIcon,
  QuestionMarkCircleIcon,
  AcademicCapIcon,
  ChatBubbleLeftRightIcon,
  ChartBarIcon,
  UsersIcon,
  TrophyIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'

const HelpCenter = ({ onClose, onStartTutorial }) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [selectedArticle, setSelectedArticle] = useState(null)

  const helpTopics = [
    {
      category: 'Getting Started',
      icon: <AcademicCapIcon className="h-6 w-6" />,
      articles: [
        {
          id: 'what-is-simulation',
          title: 'What is Supply Chain Simulation?',
          summary: 'Learn about this classic supply chain simulation and the bullwhip effect',
        },
        {
          id: 'first-game',
          title: 'How to Play Your First Game',
          summary: 'Step-by-step guide to getting started',
        },
        {
          id: 'supply-chain-basics',
          title: 'Understanding the Supply Chain',
          summary: 'Learn about roles, information flow, and cost structure',
        },
      ],
    },
    {
      category: 'AI Features',
      icon: <ChatBubbleLeftRightIcon className="h-6 w-6" />,
      articles: [
        {
          id: 'ai-suggestions',
          title: 'Using AI Suggestions',
          summary: 'Get intelligent order recommendations',
        },
        {
          id: 'pattern-analysis',
          title: 'Understanding Pattern Analysis',
          summary: 'Learn how AI detects patterns',
        },
      ],
    },
    {
      category: 'Collaboration',
      icon: <UsersIcon className="h-6 w-6" />,
      articles: [
        {
          id: 'negotiations',
          title: 'How Negotiations Work',
          summary: 'Propose and respond to negotiations',
        },
        {
          id: 'visibility-sharing',
          title: 'Visibility Sharing Guide',
          summary: 'Share data to reduce bullwhip effect',
        },
      ],
    },
    {
      category: 'Analytics',
      icon: <ChartBarIcon className="h-6 w-6" />,
      articles: [
        {
          id: 'bullwhip-effect',
          title: 'Understanding the Bullwhip Effect',
          summary: 'Why demand amplifies upstream',
        },
        {
          id: 'performance-metrics',
          title: 'Key Performance Metrics',
          summary: 'Track costs, service, and efficiency',
        },
      ],
    },
    {
      category: 'Gamification',
      icon: <TrophyIcon className="h-6 w-6" />,
      articles: [
        {
          id: 'achievements-guide',
          title: 'Achievements Guide',
          summary: 'Complete challenges and level up',
        },
        {
          id: 'leaderboards',
          title: 'Leaderboards & Rankings',
          summary: 'Compete with other users',
        },
      ],
    },
  ]

  const filteredTopics = useMemo(() => {
    if (!searchQuery && selectedCategory === 'all') {
      return helpTopics
    }

    return helpTopics
      .map((topic) => ({
        ...topic,
        articles: topic.articles.filter((article) => {
          const matchesSearch =
            !searchQuery ||
            article.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            article.summary.toLowerCase().includes(searchQuery.toLowerCase())

          const matchesCategory =
            selectedCategory === 'all' || topic.category === selectedCategory

          return matchesSearch && matchesCategory
        }),
      }))
      .filter((topic) => topic.articles.length > 0)
  }, [searchQuery, selectedCategory])

  const categories = ['all', ...helpTopics.map((t) => t.category)]

  if (selectedArticle) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
          <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-6 flex items-center justify-between">
            <div className="flex items-center">
              <BookOpenIcon className="h-8 w-8 mr-3" />
              <h2 className="text-2xl font-bold">{selectedArticle.title}</h2>
            </div>
            <button
              onClick={() => setSelectedArticle(null)}
              className="text-white hover:text-gray-200 transition-colors"
            >
              <XMarkIcon className="h-6 w-6" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            <p className="text-gray-700 text-lg mb-4">{selectedArticle.summary}</p>
            <p className="text-gray-600">Detailed article content available in the full help system...</p>
          </div>

          <div className="bg-gray-50 p-4 flex justify-between">
            <button
              onClick={() => setSelectedArticle(null)}
              className="px-4 py-2 text-gray-700 hover:text-gray-900 transition-colors"
            >
              ← Back to Help Center
            </button>
            {onStartTutorial && (
              <button
                onClick={() => {
                  setSelectedArticle(null)
                  onStartTutorial()
                }}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Start Tutorial
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
              <QuestionMarkCircleIcon className="h-10 w-10 mr-3" />
              <div>
                <h1 className="text-3xl font-bold">Help Center</h1>
                <p className="text-indigo-100">Find answers and learn how to play</p>
              </div>
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="text-white hover:text-gray-200 transition-colors"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            )}
          </div>

          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search help articles..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-3 rounded-lg border-0 text-gray-900 placeholder-gray-500 focus:ring-2 focus:ring-white"
            />
          </div>
        </div>

        <div className="bg-gray-50 px-6 py-3 border-b flex items-center space-x-2 overflow-x-auto">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                selectedCategory === cat
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-100'
              }`}
            >
              {cat === 'all' ? 'All Topics' : cat}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {onStartTutorial && (
              <button
                onClick={onStartTutorial}
                className="flex items-center p-4 bg-gradient-to-br from-indigo-50 to-purple-50 border-2 border-indigo-200 rounded-lg hover:border-indigo-400 transition-all"
              >
                <AcademicCapIcon className="h-8 w-8 text-indigo-600 mr-3" />
                <div className="text-left">
                  <div className="font-bold text-gray-900">Start Interactive Tutorial</div>
                  <div className="text-sm text-gray-600">
                    Learn the basics with a guided tour
                  </div>
                </div>
              </button>
            )}

            <button className="flex items-center p-4 bg-gradient-to-br from-green-50 to-teal-50 border-2 border-green-200 rounded-lg hover:border-green-400 transition-all">
              <ChatBubbleLeftRightIcon className="h-8 w-8 text-green-600 mr-3" />
              <div className="text-left">
                <div className="font-bold text-gray-900">Ask AI Assistant</div>
                <div className="text-sm text-gray-600">
                  Get instant answers to your questions
                </div>
              </div>
            </button>
          </div>

          {filteredTopics.length === 0 ? (
            <div className="text-center py-12">
              <MagnifyingGlassIcon className="h-16 w-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-600">No articles found matching your search</p>
              <button
                onClick={() => {
                  setSearchQuery('')
                  setSelectedCategory('all')
                }}
                className="mt-4 text-indigo-600 hover:text-indigo-700"
              >
                Clear search
              </button>
            </div>
          ) : (
            filteredTopics.map((topic) => (
              <div key={topic.category} className="mb-8">
                <div className="flex items-center mb-4">
                  <div className="text-indigo-600 mr-2">{topic.icon}</div>
                  <h2 className="text-xl font-bold text-gray-900">{topic.category}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {topic.articles.map((article) => (
                    <button
                      key={article.id}
                      onClick={() => setSelectedArticle(article)}
                      className="text-left p-4 bg-white border border-gray-200 rounded-lg hover:border-indigo-400 hover:shadow-md transition-all"
                    >
                      <div className="font-medium text-gray-900 mb-1">{article.title}</div>
                      <div className="text-sm text-gray-600">{article.summary}</div>
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default HelpCenter
