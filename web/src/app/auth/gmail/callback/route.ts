import { NextResponse, type NextRequest } from 'next/server'

// Google lands here with ?code=... . The code is useless without our client
// secret, which lives only in the API, so we hand it to the applications page
// and let the browser (which holds the Supabase session) complete the exchange.
// The state travels with it; the page checks it against what it stored before
// leaving, which is what stops someone else's code being planted on this user.
export function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get('code')
  const error = request.nextUrl.searchParams.get('error')
  const state = request.nextUrl.searchParams.get('state')
  const target = new URL('/applications', request.nextUrl.origin)

  if (error || !code) {
    target.searchParams.set('gmail', 'denied')
  } else {
    target.searchParams.set('gmail_code', code)
    target.searchParams.set('gmail_state', state ?? '')
  }
  return NextResponse.redirect(target)
}
