/**
 * InlineComments Component
 *
 * A reusable comment section that can be embedded in any order/plan detail view.
 * Supports:
 * - Threaded comments with replies
 * - @mentions with autocomplete
 * - Comment types (general, question, issue, etc.)
 * - Edit and delete functionality
 * - Pin important comments
 */

import React, { useState, useEffect, useCallback } from 'react';
import { formatDistanceToNow } from 'date-fns';
import {
  Send,
  Reply,
  Pencil,
  Trash2,
  MoreVertical,
  Pin,
  HelpCircle,
  AlertCircle,
  CheckCircle,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  User,
  X,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  IconButton,
  Badge,
  Alert,
  Spinner,
  Textarea,
  Label,
  Select,
  SelectOption,
} from './index';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

// Comment type icons and colors
const COMMENT_TYPES = {
  general: { icon: MessageSquare, color: 'secondary', label: 'General' },
  question: { icon: HelpCircle, color: 'info', label: 'Question' },
  issue: { icon: AlertCircle, color: 'destructive', label: 'Issue' },
  resolution: { icon: CheckCircle, color: 'success', label: 'Resolution' },
  approval: { icon: CheckCircle, color: 'success', label: 'Approval' },
  rejection: { icon: AlertCircle, color: 'destructive', label: 'Rejection' },
};

/**
 * Single comment item with replies
 */
const CommentItem = ({
  comment,
  currentUserId,
  onReply,
  onEdit,
  onDelete,
  onPin,
  depth = 0,
}) => {
  const [showReplies, setShowReplies] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);

  const isAuthor = comment.author_id === currentUserId;
  const typeConfig = COMMENT_TYPES[comment.comment_type] || COMMENT_TYPES.general;
  const TypeIcon = typeConfig.icon;

  return (
    <div className={cn('mb-2', depth > 0 && `ml-${Math.min(depth * 8, 16)}`)}>
      <Card
        variant={depth === 0 ? 'elevated' : 'ghost'}
        padding="sm"
        className={cn(
          comment.is_pinned && 'bg-accent border-l-4 border-l-primary'
        )}
      >
        <CardContent>
          {/* Comment header */}
          <div className="flex items-center mb-2">
            <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center mr-2">
              {comment.author_name?.[0]?.toUpperCase() || <User className="h-4 w-4" />}
            </div>
            <div className="flex-grow">
              <span className="text-sm font-medium">{comment.author_name}</span>
              {comment.author_role && (
                <Badge variant="secondary" size="sm" className="ml-2">
                  {comment.author_role}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground ml-2">
                {formatDistanceToNow(new Date(comment.created_at), { addSuffix: true })}
                {comment.is_edited && ' (edited)'}
              </span>
            </div>

            {/* Comment type badge */}
            <Badge
              variant={typeConfig.color}
              size="sm"
              icon={<TypeIcon className="h-3 w-3" />}
              className="mr-2"
            >
              {typeConfig.label}
            </Badge>

            {/* Pinned indicator */}
            {comment.is_pinned && (
              <Pin className="h-4 w-4 text-primary mr-2" />
            )}

            {/* Actions menu */}
            <div className="relative">
              <IconButton
                variant="ghost"
                size="icon"
                onClick={() => setMenuOpen(!menuOpen)}
              >
                <MoreVertical className="h-4 w-4" />
              </IconButton>

              {menuOpen && (
                <div className="absolute right-0 top-full mt-1 bg-popover border border-border rounded-md shadow-lg z-50 min-w-[150px]">
                  <button
                    className="w-full px-3 py-2 text-left text-sm hover:bg-accent flex items-center gap-2"
                    onClick={() => { onReply(comment); setMenuOpen(false); }}
                  >
                    <Reply className="h-4 w-4" /> Reply
                  </button>
                  {isAuthor && (
                    <button
                      className="w-full px-3 py-2 text-left text-sm hover:bg-accent flex items-center gap-2"
                      onClick={() => { onEdit(comment); setMenuOpen(false); }}
                    >
                      <Pencil className="h-4 w-4" /> Edit
                    </button>
                  )}
                  <button
                    className="w-full px-3 py-2 text-left text-sm hover:bg-accent flex items-center gap-2"
                    onClick={() => { onPin(comment); setMenuOpen(false); }}
                  >
                    <Pin className="h-4 w-4" />
                    {comment.is_pinned ? 'Unpin' : 'Pin'}
                  </button>
                  {isAuthor && (
                    <button
                      className="w-full px-3 py-2 text-left text-sm hover:bg-accent flex items-center gap-2 text-destructive"
                      onClick={() => { onDelete(comment); setMenuOpen(false); }}
                    >
                      <Trash2 className="h-4 w-4" /> Delete
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Comment content */}
          <p
            className="text-sm whitespace-pre-wrap"
            dangerouslySetInnerHTML={{
              __html: comment.content_html || comment.content,
            }}
          />

          {/* Mentions */}
          {comment.mentions?.length > 0 && (
            <div className="mt-2 flex gap-1 flex-wrap">
              {comment.mentions.map((mention) => (
                <Badge
                  key={mention.id}
                  variant="outline"
                  size="sm"
                >
                  @{mention.mentioned_username}
                </Badge>
              ))}
            </div>
          )}

          {/* Reply count toggle */}
          {comment.replies?.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              leftIcon={showReplies ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              onClick={() => setShowReplies(!showReplies)}
              className="mt-2"
            >
              {comment.replies.length} {comment.replies.length === 1 ? 'reply' : 'replies'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Nested replies */}
      {showReplies && comment.replies?.map((reply) => (
        <CommentItem
          key={reply.id}
          comment={reply}
          currentUserId={currentUserId}
          onReply={onReply}
          onEdit={onEdit}
          onDelete={onDelete}
          onPin={onPin}
          depth={depth + 1}
        />
      ))}
    </div>
  );
};

/**
 * Comment input form
 */
const CommentForm = ({
  onSubmit,
  replyTo,
  editingComment,
  onCancel,
  users = [],
}) => {
  const [content, setContent] = useState(editingComment?.content || '');
  const [commentType, setCommentType] = useState(editingComment?.comment_type || 'general');
  const [submitting, setSubmitting] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionSearch, setMentionSearch] = useState('');

  useEffect(() => {
    if (editingComment) {
      setContent(editingComment.content);
      setCommentType(editingComment.comment_type);
    }
  }, [editingComment]);

  const handleSubmit = async () => {
    if (!content.trim()) return;

    setSubmitting(true);
    try {
      await onSubmit({
        content: content.trim(),
        comment_type: commentType,
        parent_id: replyTo?.id,
      });
      setContent('');
      setCommentType('general');
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Ctrl+Enter
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
    // Check for @ to show mention autocomplete
    if (e.key === '@') {
      setMentionOpen(true);
    }
  };

  const handleMentionSelect = (username) => {
    setContent((prev) => prev + username + ' ');
    setMentionOpen(false);
  };

  return (
    <Card variant="ghost" className="bg-muted/50 p-4">
      <CardContent>
        {replyTo && (
          <Alert variant="info" className="mb-3" onClose={onCancel}>
            Replying to {replyTo.author_name}
          </Alert>
        )}
        {editingComment && (
          <Alert variant="warning" className="mb-3" onClose={onCancel}>
            Editing comment
          </Alert>
        )}

        <div className="flex gap-3 mb-3">
          <div className="space-y-1">
            <Label>Type</Label>
            <Select
              value={commentType}
              onChange={(e) => setCommentType(e.target.value)}
              size="sm"
              className="min-w-[140px]"
            >
              {Object.entries(COMMENT_TYPES).map(([key, config]) => (
                <SelectOption key={key} value={key}>
                  {config.label}
                </SelectOption>
              ))}
            </Select>
          </div>
        </div>

        <Textarea
          placeholder="Add a comment... Use @username to mention someone. Press Ctrl+Enter to submit."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          className="mb-3"
          rows={3}
        />

        {/* Mention autocomplete popover */}
        {mentionOpen && (
          <div className="relative">
            <div className="absolute bottom-full left-0 mb-1 bg-popover border border-border rounded-md shadow-lg z-50 min-w-[200px]">
              {users
                .filter((u) =>
                  u.name?.toLowerCase().includes(mentionSearch.toLowerCase())
                )
                .slice(0, 5)
                .map((user) => (
                  <button
                    key={user.id}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-accent flex items-center gap-2"
                    onClick={() => handleMentionSelect(user.name)}
                  >
                    <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center">
                      {user.name?.[0]}
                    </div>
                    {user.name}
                  </button>
                ))}
              <button
                className="w-full px-3 py-2 text-left text-xs text-muted-foreground hover:bg-accent"
                onClick={() => setMentionOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          {(replyTo || editingComment) && (
            <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          )}
          <Button
            rightIcon={submitting ? <Spinner size="sm" /> : <Send className="h-4 w-4" />}
            onClick={handleSubmit}
            disabled={!content.trim() || submitting}
          >
            {editingComment ? 'Update' : replyTo ? 'Reply' : 'Comment'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

/**
 * Main InlineComments component
 */
const InlineComments = ({
  entityType,
  entityId,
  title = 'Comments',
  collapsible = true,
  defaultExpanded = true,
}) => {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [replyTo, setReplyTo] = useState(null);
  const [editingComment, setEditingComment] = useState(null);
  const [users, setUsers] = useState([]);
  const [currentUserId, setCurrentUserId] = useState(null);

  // Load comments
  const loadComments = useCallback(async () => {
    if (!entityType || !entityId) return;

    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/comments', {
        params: {
          entity_type: entityType,
          entity_id: String(entityId),
          include_replies: true,
        },
      });
      setComments(response.data.comments || []);
    } catch (err) {
      console.error('Failed to load comments:', err);
      setError('Failed to load comments');
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  // Load users for @mentions
  const loadUsers = useCallback(async () => {
    try {
      const response = await api.get('/users');
      setUsers(response.data || []);
    } catch (err) {
      console.error('Failed to load users for mentions:', err);
    }
  }, []);

  // Get current user
  const loadCurrentUser = useCallback(async () => {
    try {
      const response = await api.get('/auth/me');
      setCurrentUserId(response.data.id);
    } catch (err) {
      console.error('Failed to get current user:', err);
    }
  }, []);

  useEffect(() => {
    loadComments();
    loadUsers();
    loadCurrentUser();
  }, [loadComments, loadUsers, loadCurrentUser]);

  // Create or update comment
  const handleSubmit = async (data) => {
    try {
      if (editingComment) {
        // Update existing comment
        await api.put(`/comments/${editingComment.id}`, {
          content: data.content,
        });
      } else {
        // Create new comment
        await api.post('/comments', {
          entity_type: entityType,
          entity_id: String(entityId),
          content: data.content,
          comment_type: data.comment_type,
          parent_id: data.parent_id,
        });
      }

      // Reset state and reload
      setReplyTo(null);
      setEditingComment(null);
      await loadComments();
    } catch (err) {
      console.error('Failed to save comment:', err);
      setError('Failed to save comment');
    }
  };

  // Delete comment
  const handleDelete = async (comment) => {
    if (!window.confirm('Are you sure you want to delete this comment?')) return;

    try {
      await api.delete(`/comments/${comment.id}`);
      await loadComments();
    } catch (err) {
      console.error('Failed to delete comment:', err);
      setError('Failed to delete comment');
    }
  };

  // Pin/unpin comment
  const handlePin = async (comment) => {
    try {
      await api.post(`/comments/${comment.id}/pin`);
      await loadComments();
    } catch (err) {
      console.error('Failed to pin comment:', err);
      setError('Failed to pin comment');
    }
  };

  const handleReply = (comment) => {
    setReplyTo(comment);
    setEditingComment(null);
  };

  const handleEdit = (comment) => {
    setEditingComment(comment);
    setReplyTo(null);
  };

  const handleCancel = () => {
    setReplyTo(null);
    setEditingComment(null);
  };

  // Sort comments: pinned first, then by date
  const sortedComments = [...comments].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return new Date(b.created_at) - new Date(a.created_at);
  });

  return (
    <Card className="mt-4">
      {/* Header */}
      <div
        className={cn(
          'p-4 flex items-center',
          collapsible && 'cursor-pointer',
          expanded && 'border-b border-border'
        )}
        onClick={() => collapsible && setExpanded(!expanded)}
      >
        <div className="relative mr-3">
          <MessageSquare className="h-5 w-5" />
          {comments.length > 0 && (
            <span className="absolute -top-2 -right-2 bg-primary text-primary-foreground text-xs rounded-full h-4 w-4 flex items-center justify-center">
              {comments.length}
            </span>
          )}
        </div>
        <h3 className="text-lg font-semibold flex-grow">{title}</h3>
        {collapsible && (
          <IconButton variant="ghost" size="icon">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </IconButton>
        )}
      </div>

      {expanded && (
        <CardContent className="p-4">
          {/* Error message */}
          {error && (
            <Alert variant="error" className="mb-3" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Comment form */}
          <CommentForm
            onSubmit={handleSubmit}
            replyTo={replyTo}
            editingComment={editingComment}
            onCancel={handleCancel}
            users={users}
          />

          <hr className="my-4 border-border" />

          {/* Loading state */}
          {loading ? (
            <div className="flex justify-center p-8">
              <Spinner size="lg" />
            </div>
          ) : comments.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No comments yet. Be the first to add one!
            </p>
          ) : (
            /* Comments list */
            <div>
              {sortedComments.map((comment) => (
                <CommentItem
                  key={comment.id}
                  comment={comment}
                  currentUserId={currentUserId}
                  onReply={handleReply}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                  onPin={handlePin}
                />
              ))}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
};

export default InlineComments;
