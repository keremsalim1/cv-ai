import { messageKeyForCode } from '@/lib/errors'

it('maps known codes to their message key', () => {
  expect(messageKeyForCode('SCANNED_PDF')).toBe('errors.SCANNED_PDF')
  expect(messageKeyForCode('DAILY_LIMIT_REACHED')).toBe('errors.DAILY_LIMIT_REACHED')
})

it('explains a server at browser capacity instead of falling back to UNKNOWN', () => {
  expect(messageKeyForCode('TOO_MANY_SESSIONS')).toBe('errors.TOO_MANY_SESSIONS')
})

it('names a lost Gmail grant so the UI can offer reconnection', () => {
  expect(messageKeyForCode('GMAIL_DISCONNECTED')).toBe('errors.GMAIL_DISCONNECTED')
})

it('falls back to UNKNOWN for unrecognized codes', () => {
  expect(messageKeyForCode('SOMETHING_ELSE')).toBe('errors.UNKNOWN')
})
