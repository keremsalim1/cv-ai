const KNOWN_CODES = new Set([
  'SCANNED_PDF', 'INVALID_PDF', 'FILE_TOO_LARGE', 'FETCH_FAILED', 'JOB_PARSE_FAILED',
  'NO_INPUT', 'DAILY_LIMIT_REACHED', 'AI_UNAVAILABLE', 'NOT_AUTHENTICATED',
  // assisted apply: the headed browser session died (server restart, idle GC),
  // or the server is already running as many browsers as it can host
  'SESSION_NOT_FOUND', 'FORBIDDEN', 'TOO_MANY_SESSIONS',
  // the Gmail grant is gone — the user revoked it, or never finished consent
  'GMAIL_DISCONNECTED', 'UNKNOWN',
])

export function messageKeyForCode(code: string): string {
  return `errors.${KNOWN_CODES.has(code) ? code : 'UNKNOWN'}`
}
