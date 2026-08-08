const PROTECTED_PREFIXES = ['/dashboard', '/cv', '/score', '/ats', '/applications']

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'))
}
