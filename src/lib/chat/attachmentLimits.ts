export const CHAT_MAX_ATTACHMENTS = 5;
export const CHAT_MAX_SINGLE_ATTACHMENT_BYTES = 2 * 1024 * 1024;
export const CHAT_MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024;

export const formatMegabytes = (bytes: number): string =>
  `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;
