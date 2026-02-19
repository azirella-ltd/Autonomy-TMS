export const extractStartupNotices = (payload) => {
  const notices = payload?.config?.startup_notices;
  if (!Array.isArray(notices)) {
    return [];
  }
  return notices.filter((notice) => typeof notice === 'string' && notice.trim()).map((notice) => notice.trim());
};

export const emitStartupNotices = (payload, emitter) => {
  const notices = extractStartupNotices(payload);
  if (typeof emitter !== 'function' || notices.length === 0) {
    return notices;
  }
  notices.forEach((notice) => {
    try {
      emitter(notice);
    } catch (error) {
      // Swallow UI notification errors to avoid blocking the start flow
    }
  });
  return notices;
};
