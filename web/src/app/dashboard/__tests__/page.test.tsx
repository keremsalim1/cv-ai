import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CVData } from '@/types/api'

vi.mock('next/navigation', () => {
  // stable identity, like the real useRouter — a fresh object per call re-runs
  // every effect that depends on the router
  const router = { push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }
  return { useRouter: () => router }
})

const upload = vi.fn(async () => ({ data: { path: 'p' }, error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

vi.mock('@/lib/db', () => ({
  listCvs: vi.fn(async () => []),
  insertCv: vi.fn(async () => ({ id: 'c1' })),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, parseCv: vi.fn() }
})

import { listCvs, insertCv } from '@/lib/db'
import { parseCv, ApiError } from '@/lib/api'
import DashboardPage from '@/app/dashboard/page'

const CV: CVData = {
  full_name: 'Ada', email: null, phone: null, location: null, summary: null,
  experiences: [], education: [], skills: [], languages: [], certifications: [],
}

beforeEach(() => vi.clearAllMocks())

it('shows the empty state when there are no CVs', async () => {
  renderWithIntl(<DashboardPage />)
  expect(await screen.findByText(/Henüz CV yüklemediniz/)).toBeInTheDocument()
})

it('parses, uploads to storage, and inserts a row on file pick', async () => {
  ;(parseCv as Mock).mockResolvedValue(CV)
  renderWithIntl(<DashboardPage />)
  const input = await screen.findByLabelText('CV Yükle (PDF)')
  const file = new File([new Uint8Array([1, 2])], 'cv.pdf', { type: 'application/pdf' })
  await userEvent.upload(input, file)
  await waitFor(() => expect(insertCv).toHaveBeenCalled())
  expect(parseCv).toHaveBeenCalledWith(file)
  expect(upload).toHaveBeenCalled()
  const insertedRow = (insertCv as Mock).mock.calls[0][1]
  expect(insertedRow).toMatchObject({ user_id: 'u1', is_ats: false, parsed_data: CV })
  expect(insertedRow.file_path.startsWith('u1/')).toBe(true)
  expect(listCvs).toHaveBeenCalledTimes(2) // initial load + refresh
})

it('shows a localized error when the API rejects the PDF', async () => {
  ;(parseCv as Mock).mockRejectedValue(new ApiError('SCANNED_PDF', 400))
  renderWithIntl(<DashboardPage />)
  const input = await screen.findByLabelText('CV Yükle (PDF)')
  await userEvent.upload(input, new File([new Uint8Array([1])], 'cv.pdf', { type: 'application/pdf' }))
  expect(await screen.findByText(/taranmış görünüyor/)).toBeInTheDocument()
  expect(insertCv).not.toHaveBeenCalled()
})

it('rejects oversized files client-side', async () => {
  renderWithIntl(<DashboardPage />)
  const input = await screen.findByLabelText('CV Yükle (PDF)')
  const big = new File([new ArrayBuffer(10 * 1024 * 1024 + 1)], 'cv.pdf', { type: 'application/pdf' })
  await userEvent.upload(input, big)
  expect(await screen.findByText(/10 MB/)).toBeInTheDocument()
  expect(parseCv).not.toHaveBeenCalled()
})
