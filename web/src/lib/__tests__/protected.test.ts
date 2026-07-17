import { isProtectedPath } from '@/lib/protected'

it.each([
  ['/dashboard', true],
  ['/dashboard/anything', true],
  ['/cv/abc', true],
  ['/cv/abc/score', true],
  ['/score', true],
  ['/score/anything', true],
  ['/ats', true],
  ['/ats/anything', true],
  ['/', false],
  ['/login', false],
  ['/register', false],
  ['/auth/callback', false],
  ['/cvsomething', false],
])('%s -> %s', (path, expected) => {
  expect(isProtectedPath(path)).toBe(expected)
})
