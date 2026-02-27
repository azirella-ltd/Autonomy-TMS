import { api } from './api';

const executiveBriefingApi = {
  generate: (briefingType = 'adhoc') =>
    api.post('/executive-briefing/generate', { briefing_type: briefingType }),

  getLatest: () =>
    api.get('/executive-briefing/latest'),

  getBriefing: (id) =>
    api.get(`/executive-briefing/${id}`),

  listHistory: (limit = 20, offset = 0, briefingType = null) =>
    api.get('/executive-briefing/history', {
      params: { limit, offset, ...(briefingType && { briefing_type: briefingType }) },
    }),

  askFollowup: (briefingId, question) =>
    api.post(`/executive-briefing/${briefingId}/ask`, { question }),

  getSchedule: () =>
    api.get('/executive-briefing/schedule/config'),

  updateSchedule: (config) =>
    api.put('/executive-briefing/schedule/config', config),
};

export default executiveBriefingApi;
