export const GMAIL_REDIRECT_PATH = '/auth/gmail/callback'
export const GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'

const STATE_KEY = 'gmail_oauth_state'

export function gmailConsentUrl(clientId: string, redirectUri: string, state: string): string {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: GMAIL_SCOPE,
    access_type: 'offline',
    // Google omits refresh_token on a repeat grant unless consent is forced,
    // which would leave us with a connection that dies in an hour.
    prompt: 'consent',
    include_granted_scopes: 'true',
    // Without this, anyone can hand our callback a code from their own consent
    // and the victim's account ends up reading the attacker's mailbox.
    state,
  })
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`
}

export function newOAuthState(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

/** Held in sessionStorage: it must survive the trip to Google and no longer. */
export function rememberOAuthState(state: string): void {
  if (typeof sessionStorage === 'undefined') return
  sessionStorage.setItem(STATE_KEY, state)
}

/** Reads the state and forgets it, so a replayed callback finds nothing. */
export function takeOAuthState(): string | null {
  if (typeof sessionStorage === 'undefined') return null
  const state = sessionStorage.getItem(STATE_KEY)
  sessionStorage.removeItem(STATE_KEY)
  return state
}
