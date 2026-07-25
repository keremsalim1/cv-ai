const KNOWN_CODES = new Set([
  'SCANNED_PDF', 'INVALID_PDF', 'FILE_TOO_LARGE', 'FETCH_FAILED', 'JOB_PARSE_FAILED',
  'NO_INPUT', 'DAILY_LIMIT_REACHED', 'AI_UNAVAILABLE', 'NOT_AUTHENTICATED',
  // assisted apply: the headed browser session died (server restart, idle GC)
  'SESSION_NOT_FOUND', 'FORBIDDEN', 'UNKNOWN',
])

export function messageKeyForCode(code: string): string {
  return `errors.${KNOWN_CODES.has(code) ? code : 'UNKNOWN'}`
}
