import { useState, useEffect, useRef } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Spinner,
  Textarea,
} from '../common';
import {
  Send,
  Plus,
  Reply,
  MoreVertical,
  Paperclip,
  MessageCircle,
  User,
  Users,
  Link,
  Search,
  X,
  Pin,
  Trash2,
  Pencil,
  Check,
  CheckCircle,
} from 'lucide-react';
import { api } from '../../services/api';

/**
 * TeamMessaging Component
 *
 * Features:
 * - Channel-based messaging with entity linking
 * - Threaded conversations
 * - @mentions with user autocomplete
 * - Read receipts
 * - Message pinning
 */
const TeamMessaging = () => {
  // Channel state
  const [channels, setChannels] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Message composition
  const [newMessage, setNewMessage] = useState('');
  const [replyTo, setReplyTo] = useState(null);
  const [mentionSearch, setMentionSearch] = useState('');
  const [mentionAnchor, setMentionAnchor] = useState(null);
  const [mentionUsers, setMentionUsers] = useState([]);

  // Dialogs
  const [createChannelOpen, setCreateChannelOpen] = useState(false);
  const [newChannel, setNewChannel] = useState({
    name: '',
    description: '',
    channel_type: 'group',
    linked_entity_type: '',
    linked_entity_id: '',
  });

  // Users for mentions
  const [users, setUsers] = useState([]);

  // Message menu
  const [menuOpen, setMenuOpen] = useState(null);
  const [selectedMessage, setSelectedMessage] = useState(null);

  // Thread view
  const [threadView, setThreadView] = useState(null);
  const [threadMessages, setThreadMessages] = useState([]);

  // Edit message state
  const [editingMessage, setEditingMessage] = useState(null);
  const [editContent, setEditContent] = useState('');

  const messagesEndRef = useRef(null);
  const messageInputRef = useRef(null);

  // Load channels on mount
  useEffect(() => {
    loadChannels();
    loadUsers();
  }, []);

  // Load messages when channel changes
  useEffect(() => {
    if (selectedChannel) {
      loadMessages(selectedChannel.id);
    }
  }, [selectedChannel]);

  // Scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadChannels = async () => {
    setLoading(true);
    try {
      const response = await api.get('/team-messaging/channels');
      const channelList = response.data.channels || response.data || [];
      setChannels(channelList);
      if (channelList.length > 0 && !selectedChannel) {
        setSelectedChannel(channelList[0]);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load channels');
    } finally {
      setLoading(false);
    }
  };

  const loadMessages = async (channelId) => {
    setLoading(true);
    try {
      const response = await api.get(`/team-messaging/channels/${channelId}/messages`);
      const messageList = response.data.messages || response.data || [];
      setMessages(messageList);
      // Mark messages as read
      await api.post(`/team-messaging/channels/${channelId}/mark-read`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load messages');
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const response = await api.get('/users');
      setUsers(response.data || []);
    } catch (err) {
      console.error('Failed to load users:', err);
    }
  };

  const loadThread = async (messageId) => {
    if (!selectedChannel) return;
    try {
      const response = await api.get(`/team-messaging/channels/${selectedChannel.id}/messages/${messageId}/thread`);
      setThreadMessages(response.data);
      setThreadView(messages.find(m => m.id === messageId));
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load thread');
    }
  };

  const createChannel = async () => {
    setLoading(true);
    try {
      await api.post('/team-messaging/channels', newChannel);
      setCreateChannelOpen(false);
      setNewChannel({
        name: '',
        description: '',
        channel_type: 'group',
        linked_entity_type: '',
        linked_entity_id: '',
      });
      loadChannels();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create channel');
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!newMessage.trim() || !selectedChannel) return;

    // Extract mentions from message
    const mentionRegex = /@\[([^\]]+)\]\((\d+)\)/g;
    const mentions = [];
    let match;
    while ((match = mentionRegex.exec(newMessage)) !== null) {
      mentions.push({ user_id: parseInt(match[2]), display_name: match[1] });
    }

    try {
      await api.post(`/team-messaging/channels/${selectedChannel.id}/messages`, {
        content: newMessage,
        parent_id: replyTo?.id || null,
        mentions: mentions.map(m => m.user_id),
      });
      setNewMessage('');
      setReplyTo(null);
      loadMessages(selectedChannel.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send message');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }

    // Handle @ mentions
    if (e.key === '@') {
      setMentionAnchor(e.currentTarget);
      setMentionSearch('');
      setMentionUsers(users.slice(0, 5));
    }
  };

  const handleMentionSelect = (user) => {
    const mention = `@[${user.email || user.username}](${user.id}) `;
    setNewMessage(prev => prev + mention);
    setMentionAnchor(null);
    messageInputRef.current?.focus();
  };

  const handleMessageMenu = (event, message) => {
    event.stopPropagation();
    setMenuOpen(message.id);
    setSelectedMessage(message);
  };

  const handlePinMessage = async () => {
    if (!selectedMessage || !selectedChannel) return;
    try {
      await api.post(`/team-messaging/channels/${selectedChannel.id}/messages/${selectedMessage.id}/pin`);
      loadMessages(selectedChannel.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to pin message');
    }
    setMenuOpen(null);
  };

  const handleDeleteMessage = async () => {
    if (!selectedMessage || !selectedChannel) return;
    try {
      await api.delete(`/team-messaging/channels/${selectedChannel.id}/messages/${selectedMessage.id}`);
      loadMessages(selectedChannel.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete message');
    }
    setMenuOpen(null);
  };

  const handleEditMessage = () => {
    if (!selectedMessage) return;
    setEditingMessage(selectedMessage);
    setEditContent(selectedMessage.content);
    setMenuOpen(null);
  };

  const handleSaveEdit = async () => {
    if (!editingMessage || !selectedChannel || !editContent.trim()) return;
    try {
      await api.put(`/team-messaging/channels/${selectedChannel.id}/messages/${editingMessage.id}`, {
        content: editContent,
      });
      setEditingMessage(null);
      setEditContent('');
      loadMessages(selectedChannel.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to edit message');
    }
  };

  const handleCancelEdit = () => {
    setEditingMessage(null);
    setEditContent('');
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return date.toLocaleDateString();
  };

  const getChannelIcon = (channel) => {
    if (channel.channel_type === 'direct') return <User className="h-4 w-4" />;
    if (channel.linked_entity_type) return <Link className="h-4 w-4" />;
    return <Users className="h-4 w-4" />;
  };

  const renderMessage = (message, isThread = false) => (
    <div
      key={message.id}
      className={`flex gap-3 p-3 rounded-lg mb-2 ${
        message.is_pinned ? 'bg-primary/10' : 'hover:bg-muted'
      }`}
    >
      <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-medium">
        {(message.sender_name || message.author_name)?.[0] || 'U'}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">
            {message.sender_name || message.author_name || `User ${message.sender_id || message.author_id}`}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatTime(message.created_at)}
          </span>
          {message.is_pinned && (
            <Badge variant="secondary" className="flex items-center gap-1 text-xs">
              <Pin className="h-3 w-3" />
              Pinned
            </Badge>
          )}
          {message.is_edited && (
            <span className="text-xs text-muted-foreground">(edited)</span>
          )}
        </div>
        <div
          className="text-sm mt-1 whitespace-pre-wrap"
          dangerouslySetInnerHTML={{
            __html: (message.content_html || message.content || '').replace(
              /@\[([^\]]+)\]\(\d+\)/g,
              '<span class="text-primary font-medium">@$1</span>'
            )
          }}
        />

        {/* Reply count */}
        {!isThread && message.reply_count > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => loadThread(message.id)}
          >
            <Reply className="h-3 w-3 mr-1" />
            {message.reply_count} {message.reply_count === 1 ? 'reply' : 'replies'}
          </Button>
        )}

        {/* Read receipts */}
        {message.read_by_count > 0 && (
          <div className="flex items-center gap-1 mt-1">
            <CheckCircle className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              Read by {message.read_by_count}
            </span>
          </div>
        )}
      </div>
      <div className="flex items-start gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setReplyTo(message)}
        >
          <Reply className="h-4 w-4" />
        </Button>
        <div className="relative">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={(e) => handleMessageMenu(e, message)}
          >
            <MoreVertical className="h-4 w-4" />
          </Button>
          {menuOpen === message.id && (
            <div className="absolute right-0 top-8 z-10 bg-popover border rounded-md shadow-lg py-1 min-w-[150px]">
              <button
                className="w-full px-3 py-2 text-sm text-left hover:bg-muted flex items-center gap-2"
                onClick={handleEditMessage}
              >
                <Pencil className="h-4 w-4" />
                Edit Message
              </button>
              <button
                className="w-full px-3 py-2 text-sm text-left hover:bg-muted flex items-center gap-2"
                onClick={handlePinMessage}
              >
                <Pin className="h-4 w-4" />
                {message.is_pinned ? 'Unpin' : 'Pin'} Message
              </button>
              <button
                className="w-full px-3 py-2 text-sm text-left hover:bg-muted flex items-center gap-2 text-destructive"
                onClick={handleDeleteMessage}
              >
                <Trash2 className="h-4 w-4" />
                Delete Message
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="h-full flex flex-col">
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
          <Button variant="ghost" size="icon" className="ml-auto" onClick={() => setError(null)}>
            <X className="h-4 w-4" />
          </Button>
        </Alert>
      )}

      <div className="flex-1 flex gap-4 min-h-0">
        {/* Channel List */}
        <Card className="w-72 flex-shrink-0 flex flex-col">
          <div className="p-4 border-b flex justify-between items-center">
            <h3 className="font-semibold">Channels</h3>
            <Button variant="ghost" size="icon" onClick={() => setCreateChannelOpen(true)}>
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {channels.map((channel) => (
              <button
                key={channel.id}
                className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-muted text-left ${
                  selectedChannel?.id === channel.id ? 'bg-muted' : ''
                }`}
                onClick={() => setSelectedChannel(channel)}
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  selectedChannel?.id === channel.id ? 'bg-primary text-primary-foreground' : 'bg-secondary'
                }`}>
                  {getChannelIcon(channel)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{channel.name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {channel.linked_entity_type ? `Linked: ${channel.linked_entity_type}` : channel.description}
                  </p>
                </div>
                {channel.unread_count > 0 && (
                  <Badge variant="destructive">{channel.unread_count}</Badge>
                )}
              </button>
            ))}

            {channels.length === 0 && !loading && (
              <div className="p-8 text-center">
                <MessageCircle className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                <p className="text-muted-foreground mb-2">No channels yet</p>
                <Button onClick={() => setCreateChannelOpen(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Create Channel
                </Button>
              </div>
            )}
          </div>
        </Card>

        {/* Message Area */}
        <Card className={`flex-1 flex flex-col ${threadView ? '' : ''}`}>
          {selectedChannel ? (
            <>
              {/* Channel Header */}
              <div className="p-4 border-b">
                <h3 className="font-semibold"># {selectedChannel.name}</h3>
                {selectedChannel.description && (
                  <p className="text-sm text-muted-foreground">{selectedChannel.description}</p>
                )}
                {selectedChannel.linked_entity_type && (
                  <Badge variant="outline" className="mt-2">
                    <Link className="h-3 w-3 mr-1" />
                    {selectedChannel.linked_entity_type}: {selectedChannel.linked_entity_id}
                  </Badge>
                )}
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4">
                {loading ? (
                  <div className="flex justify-center py-8">
                    <Spinner size="lg" />
                  </div>
                ) : (
                  <>
                    {messages.map((message) => renderMessage(message))}
                    <div ref={messagesEndRef} />
                  </>
                )}

                {messages.length === 0 && !loading && (
                  <div className="text-center py-8">
                    <MessageCircle className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-muted-foreground">
                      No messages yet. Start the conversation!
                    </p>
                  </div>
                )}
              </div>

              {/* Reply indicator */}
              {replyTo && (
                <div className="px-4 py-2 bg-muted flex items-center">
                  <Reply className="h-4 w-4 mr-2" />
                  <span className="text-sm flex-1">
                    Replying to {replyTo.sender_name || replyTo.author_name || `User ${replyTo.sender_id || replyTo.author_id}`}
                  </span>
                  <Button variant="ghost" size="icon" onClick={() => setReplyTo(null)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}

              {/* Message Input */}
              <div className="p-4 border-t">
                <div className="flex gap-2">
                  <Textarea
                    placeholder={`Message #${selectedChannel.name}... (Use @ to mention)`}
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    onKeyDown={handleKeyDown}
                    ref={messageInputRef}
                    className="flex-1 min-h-[40px] max-h-[120px] resize-none"
                    rows={1}
                  />
                  <Button onClick={sendMessage} disabled={!newMessage.trim()}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <MessageCircle className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-muted-foreground">
                  Select a channel to start messaging
                </h3>
              </div>
            </div>
          )}
        </Card>

        {/* Thread View */}
        {threadView && (
          <Card className="w-80 flex-shrink-0 flex flex-col">
            <div className="p-4 border-b flex justify-between items-center">
              <h3 className="font-semibold">Thread</h3>
              <Button variant="ghost" size="icon" onClick={() => setThreadView(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {/* Original message */}
              <Card className="mb-4">
                <CardContent className="p-4">
                  <p className="font-medium text-sm">{threadView.sender_name || threadView.author_name}</p>
                  <p className="text-sm mt-1">{threadView.content}</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {formatTime(threadView.created_at)}
                  </p>
                </CardContent>
              </Card>

              <div className="flex items-center gap-2 my-4">
                <hr className="flex-1" />
                <Badge variant="secondary">{threadMessages.length} replies</Badge>
                <hr className="flex-1" />
              </div>

              {threadMessages.map((message) => renderMessage(message, true))}
            </div>

            {/* Thread reply input */}
            <div className="p-4 border-t">
              <Textarea
                placeholder="Reply in thread..."
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    setReplyTo(threadView);
                    sendMessage();
                  }
                }}
                className="min-h-[40px] resize-none"
                rows={1}
              />
            </div>
          </Card>
        )}
      </div>

      {/* Create Channel Dialog */}
      <Dialog open={createChannelOpen} onOpenChange={setCreateChannelOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Channel</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <Label htmlFor="channel-name">Channel Name</Label>
              <Input
                id="channel-name"
                value={newChannel.name}
                onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="channel-desc">Description</Label>
              <Textarea
                id="channel-desc"
                value={newChannel.description}
                onChange={(e) => setNewChannel({ ...newChannel, description: e.target.value })}
                rows={2}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="channel-type">Channel Type</Label>
              <select
                id="channel-type"
                value={newChannel.channel_type}
                onChange={(e) => setNewChannel({ ...newChannel, channel_type: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="group">Group</option>
                <option value="direct">Direct Message</option>
                <option value="entity">Entity-Linked</option>
              </select>
            </div>

            {newChannel.channel_type === 'entity' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="entity-type">Entity Type</Label>
                  <select
                    id="entity-type"
                    value={newChannel.linked_entity_type}
                    onChange={(e) => setNewChannel({ ...newChannel, linked_entity_type: e.target.value })}
                    className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                  >
                    <option value="">Select type</option>
                    <option value="purchase_order">Purchase Order</option>
                    <option value="transfer_order">Transfer Order</option>
                    <option value="supply_plan">Supply Plan</option>
                    <option value="recommendation">Recommendation</option>
                    <option value="demand_plan">Demand Plan</option>
                  </select>
                </div>
                <div>
                  <Label htmlFor="entity-id">Entity ID</Label>
                  <Input
                    id="entity-id"
                    value={newChannel.linked_entity_id}
                    onChange={(e) => setNewChannel({ ...newChannel, linked_entity_id: e.target.value })}
                    className="mt-1"
                  />
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateChannelOpen(false)}>
              Cancel
            </Button>
            <Button onClick={createChannel} disabled={!newChannel.name || loading}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Message Dialog */}
      <Dialog open={!!editingMessage} onOpenChange={() => handleCancelEdit()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Message</DialogTitle>
          </DialogHeader>
          <Textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={4}
            className="mt-4"
          />
          <DialogFooter>
            <Button variant="outline" onClick={handleCancelEdit}>
              Cancel
            </Button>
            <Button onClick={handleSaveEdit} disabled={!editContent.trim()}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default TeamMessaging;
