/**
 * TMS Conversations Client Adapter
 *
 * Implements the @azirella-ltd/autonomy-frontend ConversationsClient interface against
 * the existing TMS /comments and /users endpoints. The shared
 * <Conversation> component consumes this via <ConversationsProvider>.
 *
 * Method names match the package contract; the bodies delegate to the
 * existing TMS backend endpoints.
 */
import { api } from './api';

export const tmsConversationsClient = {
  /**
   * Fetch all comments (with replies) for an entity.
   */
  list: async (entityType, entityId) => {
    const response = await api.get('/comments', {
      params: {
        entity_type: entityType,
        entity_id: String(entityId),
        include_replies: true,
      },
    });
    return response.data?.comments || [];
  },

  /**
   * Create a new comment. Returns the created comment.
   */
  create: async (input) => {
    const response = await api.post('/comments', {
      entity_type: input.entity_type,
      entity_id: String(input.entity_id),
      content: input.content,
      comment_type: input.comment_type || 'general',
      parent_id: input.parent_id ?? null,
    });
    return response.data;
  },

  /**
   * Update a comment's content.
   */
  update: async (id, content) => {
    const response = await api.put(`/comments/${id}`, { content });
    return response.data;
  },

  /**
   * Soft-delete a comment.
   */
  delete: async (id) => {
    await api.delete(`/comments/${id}`);
  },

  /**
   * Toggle pin state.
   */
  pin: async (id) => {
    await api.post(`/comments/${id}/pin`);
  },

  /**
   * Return mentionable users. In v0.5 this is humans only — v0.7 will
   * mark agent users with `is_agent: true` so the package's mention
   * autocomplete renders them distinctly.
   */
  listMentionableUsers: async () => {
    const response = await api.get('/users');
    const users = response.data || [];
    return users.map((u) => ({
      id: u.id,
      name: u.full_name || u.username || u.name || u.email,
      role: u.role || null,
      // is_agent will become true once v0.7 provisioning creates synthetic
      // agent user rows. Default false for now.
      is_agent: u.is_agent === true,
    }));
  },

  /**
   * Return the current user's id for authorship checks.
   */
  getCurrentUserId: async () => {
    const response = await api.get('/auth/me');
    return response.data?.id;
  },
};

export default tmsConversationsClient;
