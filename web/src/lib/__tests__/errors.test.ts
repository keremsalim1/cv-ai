import { messageKeyForCode } from '@/lib/errors'

it('maps known codes to their message key', () => {
  expect(messageKeyForCode('SCANNED_PDF')).toBe('errors.SCANNED_PDF')
  expect(messageKeyForCode('DAILY_LIMIT_REACHED')).toBe('errors.DAILY_LIMIT_REACHED')
})

it('falls back to UNKNOWN for unrecognized codes', () => {
  expect(messageKeyForCode('SOMETHING_ELSE')).toBe('errors.UNKNOWN')
})
