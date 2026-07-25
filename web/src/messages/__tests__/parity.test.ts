import tr from '@/messages/tr.json'
import en from '@/messages/en.json'

function flat(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? flat(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]
  )
}

it('tr and en have identical message keys', () => {
  expect(flat(tr).sort()).toEqual(flat(en).sort())
})

it('all backend error codes are localized', () => {
  const codes = ['SCANNED_PDF', 'INVALID_PDF', 'FILE_TOO_LARGE', 'FETCH_FAILED',
    'NO_INPUT', 'DAILY_LIMIT_REACHED', 'AI_UNAVAILABLE', 'NOT_AUTHENTICATED',
    'SESSION_NOT_FOUND', 'FORBIDDEN', 'UNKNOWN']
  for (const code of codes) {
    expect(tr.errors).toHaveProperty(code)
    expect(en.errors).toHaveProperty(code)
  }
})
