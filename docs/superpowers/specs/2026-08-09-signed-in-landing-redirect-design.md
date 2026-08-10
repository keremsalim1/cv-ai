# Signed-in Visitors Land on the Panel

**Goal:** A signed-in user who opens `/`, `/login` or `/register` arrives at
`/dashboard` instead of the marketing page or an empty sign-in form — with no
flash of the page they were never meant to see.

**Non-goals.** No change to the marketing page itself, the sign-in and
registration forms, the nav bar, or the panel. No new "signed-in home" view:
`/dashboard` already is that page, and a second one would only duplicate it.

## Why the proxy, and not the page

`src/proxy.ts` (Next 16's replacement for `middleware.ts`) already runs on every
non-static request, already reads the session, and already redirects in one
direction:

```ts
if (!user && isProtectedPath(request.nextUrl.pathname)) → /login
```

What is missing is the mirror of that rule. Putting it anywhere else costs
something concrete:

- **In the page component.** `src/app/page.tsx` is a client component. A
  `useEffect` redirect renders the marketing page first and jumps afterwards,
  which is half of the reported bug rather than a fix for it.
- **In the nav bar.** Making the wordmark's `href` conditional would leave the
  same rule living in two places, free to drift apart. With the redirect in
  place the wordmark can keep pointing at `/`, and the proxy sends the user on.

The proxy also already holds the session for this request, so the rule costs no
extra Supabase round-trip.

## The rule

`src/lib/protected.ts` gains a second predicate beside `isProtectedPath`:

```ts
const GUEST_ONLY_PATHS = ['/', '/login', '/register']

export function isGuestOnlyPath(pathname: string): boolean {
  return GUEST_ONLY_PATHS.includes(pathname)
}
```

**Exact match, not prefix.** `isProtectedPath` matches on prefixes, but `/` as a
prefix matches every path in the application. Guest-only paths are therefore
compared exactly. The visible consequence is that a future `/register/confirm`
would not be caught; a test pins the exactness so the choice is deliberate
rather than accidental.

`src/proxy.ts` gains the mirror branch, directly after the existing one:

```ts
if (user && isGuestOnlyPath(request.nextUrl.pathname)) {
  const url = request.nextUrl.clone()
  url.pathname = '/dashboard'
  return NextResponse.redirect(url)
}
```

## The adjacent gap

`PROTECTED_PREFIXES` lists `/dashboard`, `/cv`, `/score`, `/ats` and
`/applications` — but not `/optimize`, which is a signed-in-only route. A signed
-out visitor opening `/optimize` is not redirected by the proxy today. The page
guards itself, so nothing leaks, but the protection layer has a hole in exactly
the file this change touches. `/optimize` joins the list, with a test line.

## Testing

Both suites follow patterns already in the repo.

**`src/lib/__tests__/protected.test.ts`** — extend the existing table:
`/`, `/login`, `/register` are guest-only; `/dashboard`, `/cv/abc`, `/loginx`
and `/registered` are not. Add `/optimize` to the protected-path table.

**`src/lib/__tests__/proxy.test.ts`** (new) — build a `NextRequest`, call
`proxy()`, read the `location` header, the way
`src/lib/__tests__/gmailCallback.test.ts` already does for a route handler.
`@supabase/ssr` is mocked so `getUser()` returns a user or `null` per case:

| Session | Path | Expected |
|---|---|---|
| signed in | `/` | redirect to `/dashboard` |
| signed in | `/login` | redirect to `/dashboard` |
| signed out | `/` | no redirect |
| signed in | `/dashboard` | no redirect |
| signed out | `/dashboard` | redirect to `/login` |

The fourth row is the one that matters most: were `/dashboard` ever treated as a
guest-only path, the two rules would bounce the user between each other forever.
The fifth row pins the behaviour that already exists, so this change cannot
quietly remove it.

## Risks

The redirect makes the marketing page unreachable for a signed-in user, which is
the intent — but it also means there is no way to view it while signed in short
of signing out. If that ever matters (showing the landing page to a customer,
for instance), the answer is a separate public URL, not a weakening of this rule.
