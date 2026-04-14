/**
 * TMS's AzirellaClient implementation.
 *
 * Implements the AzirellaClient interface from @azirella-ltd/autonomy-frontend
 * against TMS's /decision-stream/chat backend endpoint. Same contract as
 * Autonomy-SCP's scpAzirellaClient.js.
 *
 * Wire via <AzirellaProvider client={tmsAzirellaClient} config={tmsAzirellaConfig}>
 * at the app root.
 */
import { api } from './api';

export const tmsAzirellaClient = {
  async sendMessage(content, context = {}) {
    const resp = await api.post('/decision-stream/chat', {
      message: content,
      conversation_id: context.conversationId || null,
      config_id: context.configId || null,
    });

    const answer = resp.data?.response || resp.data?.content || 'No response.';

    return {
      message: {
        role: 'assistant',
        content: answer,
        timestamp: Date.now(),
        metadata: {
          conversationId: resp.data?.conversation_id,
        },
      },
    };
  },

  async clearHistory() {
    // TMS doesn't have a clear endpoint yet
  },
};

export const tmsAzirellaConfig = {
  productName: 'TMS',
  avatarSrc: '/Azirella_logo.png',
  wakeWords: [
    'hey autonomy', 'hi autonomy',
    'hey azirella', 'hi azirella',
    'hey azerella', 'hi azerella',
    'autonomy', 'azirella',
  ],
  panelDefaultWidth: 380,
  enableVoice: true,
};
