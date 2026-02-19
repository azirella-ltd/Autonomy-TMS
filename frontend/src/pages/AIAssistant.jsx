/**
 * AI Assistant Dashboard
 *
 * Claude-powered AI assistant for supply chain management (inspired by Amazon Q).
 */

import React, { useState } from 'react';
import { Badge, Button, Card, CardContent, Input } from '../components/common';
import {
  Bot,
  Send,
  Brain,
  Lightbulb,
  TrendingUp,
  HelpCircle,
} from 'lucide-react';

const AIAssistant = () => {
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m Claude, your AI supply chain assistant. How can I help you optimize your supply chain today?',
    },
  ]);

  const handleSendMessage = () => {
    if (!message.trim()) return;

    const userMessage = { role: 'user', content: message };
    setChatHistory([...chatHistory, userMessage]);

    // Mock AI response
    setTimeout(() => {
      const aiResponse = {
        role: 'assistant',
        content: 'I can help you with supply chain optimization, demand forecasting, inventory analysis, and more. This feature is currently in development and will provide real-time AI assistance soon.',
      };
      setChatHistory((prev) => [...prev, aiResponse]);
    }, 1000);

    setMessage('');
  };

  const suggestedQuestions = [
    'What is my current inventory position?',
    'How can I reduce the bullwhip effect?',
    'What is the optimal order quantity for my retailer?',
    'Analyze my supply chain performance',
    'What are the key risks in my network?',
  ];

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-6 flex items-center gap-3">
        <Bot className="h-10 w-10 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">AI Assistant</h1>
          <p className="text-sm text-muted-foreground">
            Powered by Claude • Supply Chain Intelligence
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card className="h-[600px] flex flex-col">
            {/* Chat Messages */}
            <div className="flex-1 p-6 overflow-y-auto bg-muted/30">
              {chatHistory.map((msg, index) => (
                <div
                  key={index}
                  className={`flex gap-3 mb-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-secondary'
                    }`}
                  >
                    {msg.role === 'user' ? 'U' : <Bot className="h-5 w-5" />}
                  </div>
                  <div
                    className={`max-w-[70%] p-3 rounded-lg ${
                      msg.role === 'user'
                        ? 'bg-primary/10 text-foreground'
                        : 'bg-card border'
                    }`}
                  >
                    <p className="text-sm">{msg.content}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Input Area */}
            <div className="p-4 border-t">
              <div className="flex gap-2">
                <Input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder="Ask me anything about your supply chain..."
                  className="flex-1"
                />
                <Button onClick={handleSendMessage}>
                  <Send className="h-4 w-4 mr-2" />
                  Send
                </Button>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Capabilities</h3>
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <Brain className="h-5 w-5 text-primary mt-0.5" />
                  <div>
                    <p className="font-medium text-sm">Supply Chain Analysis</p>
                    <p className="text-xs text-muted-foreground">Deep insights into your network</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <TrendingUp className="h-5 w-5 text-primary mt-0.5" />
                  <div>
                    <p className="font-medium text-sm">Demand Forecasting</p>
                    <p className="text-xs text-muted-foreground">AI-powered predictions</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Lightbulb className="h-5 w-5 text-primary mt-0.5" />
                  <div>
                    <p className="font-medium text-sm">Optimization Tips</p>
                    <p className="text-xs text-muted-foreground">Actionable recommendations</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-4">
                <HelpCircle className="h-5 w-5 text-muted-foreground" />
                <h3 className="text-lg font-semibold">Suggested Questions</h3>
              </div>
              <div className="flex flex-col gap-2">
                {suggestedQuestions.map((question, index) => (
                  <Badge
                    key={index}
                    variant="outline"
                    className="justify-start cursor-pointer hover:bg-muted py-2 px-3 text-left"
                    onClick={() => setMessage(question)}
                  >
                    {question}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card className="mt-6 bg-blue-50 dark:bg-blue-950 border-blue-200">
        <CardContent className="py-6 text-center">
          <h3 className="text-lg font-semibold mb-2">Coming Soon: Full Claude Integration</h3>
          <p className="text-sm text-muted-foreground">
            This AI Assistant will integrate with Claude API to provide real-time, context-aware
            supply chain guidance, optimization recommendations, and natural language insights.
            It will have access to your game data, supply chain configurations, and ML model outputs.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default AIAssistant;
