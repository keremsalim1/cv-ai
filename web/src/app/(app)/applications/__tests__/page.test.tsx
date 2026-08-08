import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import ApplicationsPage from '../page'

const searchParams = new URLSearchParams()
vi.mock('next/navigation', () => {
  const router = { push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }
  return { useRouter: () => router, useSearchParams: () => searchParams }
})

const listApplications = vi.fn()
const listApplicationEvents = vi.fn()
vi.mock('@/lib/db', () => ({
  listApplications: (...a: unknown[]) => listApplications(...a),
  listApplicationEvents: (...a: unknown[]) => listApplicationEvents(...a),
}))

const inboxStatus = vi.fn()
const inboxSync = vi.fn()
const inboxConnect = vi.fn()
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  inboxStatus: (...a: unknown[]) => inboxStatus(...a),
  inboxSync: (...a: unknown[]) => inboxSync(...a),
  inboxConnect: (...a: unknown[]) => inboxConnect(...a),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) } }),
}))

const application = (over = {}) => ({
  id: 'a1', user_id: 'u1', url: 'https://acme.com/j', company: 'Acme',
  title: 'Backend Engineer', stage: 'rejected', stage_updated_at: '2026-07-27T10:00:00Z',
  source: 'email', status: 'external', cv_id: null, optimized_cv_id: null,
  job_text: null, cover_letter: null, qa: {}, changes: [],
  created_at: '2026-07-20T10:00:00Z', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  for (const k of [...searchParams.keys()]) searchParams.delete(k)
  listApplications.mockResolvedValue([])
  listApplicationEvents.mockResolvedValue([])
  inboxStatus.mockResolvedValue({ connected: true, email: 'ada@example.com',
    last_synced_at: new Date().toISOString(), status: 'active' })
  inboxSync.mockResolvedValue({ scanned: 0, classified: 0, created: 0, updated: [], partial: false })
})

it('offers to connect Gmail when no mailbox is linked', async () => {
  inboxStatus.mockResolvedValue({ connected: false, email: null, last_synced_at: null, status: null })
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByRole('button', { name: "Gmail'i bağla" })).toBeInTheDocument()
  expect(screen.getByText(/kişisel yazışmalarını indirmeyiz/)).toBeInTheDocument()
})

it('shows each application with its stage', async () => {
  listApplications.mockResolvedValue([application()])
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByText('Acme')).toBeInTheDocument()
  expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
  expect(screen.getByText('Ret')).toBeInTheDocument()
})

it('still lists applications when the inbox status call fails', async () => {
  // The mailbox is an optional add-on. An assisted application is written to
  // the database by the browser and owes the inbox nothing, so a failing
  // /inbox/status must not take the list down with it.
  inboxStatus.mockRejectedValue(new Error('inbox unavailable'))
  listApplications.mockResolvedValue([application()])

  renderWithIntl(<ApplicationsPage />)

  expect(await screen.findByText('Acme')).toBeInTheDocument()
})

it('reveals the email behind a stage when asked why', async () => {
  listApplications.mockResolvedValue([application()])
  listApplicationEvents.mockResolvedValue([{
    id: 'e1', subject: 'Update on your application', from_address: 'no-reply@greenhouse.io',
    received_at: '2026-07-27T10:00:00Z', detected_stage: 'rejected',
    evidence: 'We have decided to move forward with other candidates.',
  }])
  renderWithIntl(<ApplicationsPage />)

  await userEvent.click(await screen.findByRole('button', { name: 'Neden?' }))

  expect(await screen.findByText(/move forward with other candidates/)).toBeInTheDocument()
  expect(screen.getByText(/no-reply@greenhouse.io/)).toBeInTheDocument()
})

it('syncs on demand and reloads the list', async () => {
  listApplications.mockResolvedValue([application()])
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Acme')
  listApplications.mockClear()

  await userEvent.click(screen.getByRole('button', { name: 'Yenile' }))

  await waitFor(() => expect(inboxSync).toHaveBeenCalled())
  await waitFor(() => expect(listApplications).toHaveBeenCalled())
})

it('does not sync on open when the last scan is recent', async () => {
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Başvurularım')
  await waitFor(() => expect(inboxStatus).toHaveBeenCalled())
  expect(inboxSync).not.toHaveBeenCalled()
})

it('syncs on open when the last scan is stale', async () => {
  inboxStatus.mockResolvedValue({
    connected: true, email: 'ada@example.com', status: 'active',
    last_synced_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  })
  renderWithIntl(<ApplicationsPage />)
  await waitFor(() => expect(inboxSync).toHaveBeenCalled())
})

it('tells the user when the connection has been revoked', async () => {
  inboxStatus.mockResolvedValue({ connected: true, email: 'ada@example.com',
    last_synced_at: null, status: 'revoked' })
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByText(/Gmail bağlantın sona ermiş/)).toBeInTheDocument()
})

it('says so when a sync was cut short', async () => {
  inboxSync.mockResolvedValue({ scanned: 5, classified: 2, created: 0, updated: [], partial: true })
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Başvurularım')
  await userEvent.click(screen.getByRole('button', { name: 'Yenile' }))
  expect(await screen.findByText(/Kısmen güncellendi/)).toBeInTheDocument()
})

it('exchanges the code when the returned state matches the one we stored', async () => {
  sessionStorage.setItem('gmail_oauth_state', 'st-1')
  searchParams.set('gmail_code', 'auth-code')
  searchParams.set('gmail_state', 'st-1')

  renderWithIntl(<ApplicationsPage />)

  await waitFor(() => expect(inboxConnect).toHaveBeenCalledWith(
    'auth-code', expect.stringContaining('/auth/gmail/callback')
  ))
})

it('refuses a code whose state we never issued', async () => {
  // Someone else's authorization code, walked into our callback. Exchanging it
  // would attach the attacker's mailbox to this account.
  sessionStorage.setItem('gmail_oauth_state', 'st-mine')
  searchParams.set('gmail_code', 'attacker-code')
  searchParams.set('gmail_state', 'st-theirs')

  renderWithIntl(<ApplicationsPage />)

  expect(await screen.findByText(/izin verilmedi/)).toBeInTheDocument()
  expect(inboxConnect).not.toHaveBeenCalled()
})

it('refuses a code when no flow was started in this tab', async () => {
  searchParams.set('gmail_code', 'auth-code')
  searchParams.set('gmail_state', 'st-1')

  renderWithIntl(<ApplicationsPage />)

  expect(await screen.findByText(/izin verilmedi/)).toBeInTheDocument()
  expect(inboxConnect).not.toHaveBeenCalled()
})
