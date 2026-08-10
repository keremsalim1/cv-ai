const PROTECTED_PREFIXES = ['/dashboard', '/cv', '/score', '/ats', '/applications', '/optimize']

// Exact match, not prefix: '/' as a prefix would swallow every path in the app.
const GUEST_ONLY_PATHS = ['/', '/login', '/register']

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'))
}

export function isGuestOnlyPath(pathname: string): boolean {
  return GUEST_ONLY_PATHS.includes(pathname)
}
