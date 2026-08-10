import { isGuestOnlyPath, isProtectedPath } from '@/lib/protected'

it.each([
  ['/dashboard', true],
  ['/dashboard/anything', true],
  ['/cv/abc', true],
  ['/cv/abc/score', true],
  ['/score', true],
  ['/score/anything', true],
  ['/ats', true],
  ['/ats/anything', true],
  ['/optimize', true],
  ['/optimize/anything', true],
  ['/', false],
  ['/login', false],
  ['/register', false],
  ['/auth/callback', false],
  ['/cvsomething', false],
])('isProtectedPath %s -> %s', (path, expected) => {
  expect(isProtectedPath(path)).toBe(expected)
})

it.each([
  ['/', true],
  ['/login', true],
  ['/register', true],
  ['/dashboard', false],
  ['/cv/abc', false],
  ['/optimize', false],
  ['/auth/callback', false],
  // Exact match, not prefix: these must not be caught.
  ['/loginx', false],
  ['/registered', false],
  ['/login/reset', false],
])('isGuestOnlyPath %s -> %s', (path, expected) => {
  expect(isGuestOnlyPath(path)).toBe(expected)
})
