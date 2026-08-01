import { describe, expect, it } from 'vitest'
import {
  gmailConsentUrl, newOAuthState, rememberOAuthState, takeOAuthState,
} from '@/lib/gmailOAuth'

describe('gmailConsentUrl', () => {
  const url = () =>
    new URL(gmailConsentUrl('client-123', 'http://localhost:3000/auth/gmail/callback', 'st-1'))

  it('asks for offline access so the token survives the session', () => {
    expect(url().searchParams.get('access_type')).toBe('offline')
  })

  it('forces the consent screen so Google always returns a refresh token', () => {
    // Without this, a repeat grant omits refresh_token and the connection dies silently.
    expect(url().searchParams.get('prompt')).toBe('consent')
  })

  it('requests read-only Gmail and nothing else', () => {
    expect(url().searchParams.get('scope')).toBe('https://www.googleapis.com/auth/gmail.readonly')
  })

  it('carries the client id and redirect', () => {
    expect(url().searchParams.get('client_id')).toBe('client-123')
    expect(url().searchParams.get('redirect_uri')).toBe('http://localhost:3000/auth/gmail/callback')
    expect(url().searchParams.get('response_type')).toBe('code')
  })

  it('carries the state so a code from someone else cannot be planted on us', () => {
    expect(url().searchParams.get('state')).toBe('st-1')
  })
})

describe('the OAuth state', () => {
  it('is different every time', () => {
    const states = new Set(Array.from({ length: 20 }, newOAuthState))
    expect(states.size).toBe(20)
  })

  it('is long enough not to be guessed', () => {
    expect(newOAuthState().length).toBeGreaterThanOrEqual(32)
  })

  it('comes back exactly once', () => {
    rememberOAuthState('st-1')
    expect(takeOAuthState()).toBe('st-1')
    // A replayed callback must not find a state waiting for it.
    expect(takeOAuthState()).toBeNull()
  })

  it('is null when the flow never started in this tab', () => {
    sessionStorage.clear()
    expect(takeOAuthState()).toBeNull()
  })
})
