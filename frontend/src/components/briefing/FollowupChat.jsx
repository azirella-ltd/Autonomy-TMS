import React, { useState } from 'react';
import { Send, MessageSquare, Loader2, User, Bot } from 'lucide-react';
import executiveBriefingApi from '../../services/executiveBriefingApi';

export default function FollowupChat({ briefingId, existingFollowups = [] }) {
  const [followups, setFollowups] = useState(existingFollowups);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim() || loading || !briefingId) return;

    const q = question.trim();
    setQuestion('');
    setLoading(true);

    try {
      const { data: resp } = await executiveBriefingApi.askFollowup(briefingId, q);
      if (resp.success && resp.data) {
        setFollowups((prev) => [...prev, resp.data]);
      }
    } catch (error) {
      console.error('Follow-up failed:', error);
      setFollowups((prev) => [
        ...prev,
        {
          question: q,
          answer: 'Sorry, I was unable to process your question. Please try again.',
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border rounded-lg bg-card">
      <div className="flex items-center gap-2 p-4 border-b">
        <MessageSquare className="h-5 w-5 text-primary" />
        <h3 className="font-semibold">Ask the Briefing</h3>
        <span className="text-sm text-muted-foreground">
          Drill into any topic from this briefing
        </span>
      </div>

      {/* Conversation history */}
      {followups.length > 0 && (
        <div className="p-4 space-y-4 max-h-96 overflow-y-auto">
          {followups.map((fu, idx) => (
            <div key={idx} className="space-y-2">
              <div className="flex items-start gap-2">
                <User className="h-4 w-4 mt-1 text-muted-foreground flex-shrink-0" />
                <p className="text-sm font-medium">{fu.question}</p>
              </div>
              <div className="flex items-start gap-2 ml-2">
                <Bot className="h-4 w-4 mt-1 text-primary flex-shrink-0" />
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{fu.answer}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a follow-up question..."
          disabled={loading || !briefingId}
          className="flex-1 px-3 py-2 border rounded-md text-sm bg-background
                     focus:outline-none focus:ring-2 focus:ring-primary/20
                     disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !question.trim() || !briefingId}
          className="px-3 py-2 bg-primary text-primary-foreground rounded-md
                     hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed
                     flex items-center gap-1 text-sm"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </form>
    </div>
  );
}
