import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

// Stable identities: the page's useCallback/useEffect depend on these; a fresh
// object per render causes an infinite re-render loop (same trap as the
// dashboard useRouter fix on Jul 16).
const ROUTER = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
const PARAMS = new URLSearchParams('cv=c2')
vi.mock('next/navigation', () => ({
  useRouter: () => ROUTER,
  useSearchParams: () => PARAMS,
}))

const upload = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

const CVS: CvRow[] = [
  {
    id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
    created_at: '2026-07-12T00:00:00Z',
    parsed_data: {
      full_name: 'Ada', email: null, phone: null, location: null, summary: null,
      experiences: [], education: [], skills: [], languages: [], certifications: [],
    },
  },
  {
    id: 'c2', user_id: 'u1', file_path: 'u1/b.pdf', is_ats: false, source_cv_id: null,
    created_at: '2026-07-13T00:00:00Z',
    parsed_data: {
      full_name: 'Grace', email: null, phone: null, location: null, summary: null,
      experiences: [], education: [], skills: [], languages: [], certifications: [],
    },
  },
]

vi.mock('@/lib/db', () => ({
  listCvs: vi.fn(async () => CVS),
  insertCv: vi.fn(async () => CVS[0]),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, atsRewrite: vi.fn(), atsPdf: vi.fn() }
})

vi.mock('@/lib/download', () => ({ downloadBlob: vi.fn() }))

import { insertCv, listCvs } from '@/lib/db'
import { atsRewrite, atsPdf } from '@/lib/api'
import { downloadBlob } from '@/lib/download'
import AtsPage from '@/app/(app)/ats/page'

beforeEach(() => vi.clearAllMocks())

it('preselects the CV from the query param', async () => {
  renderWithIntl(<AtsPage />)
  const select = await screen.findByLabelText('CV')
  expect((select as HTMLSelectElement).value).toBe('c2')
})

it('converts, downloads the PDF and saves the ATS copy', async () => {
  ;(atsRewrite as Mock).mockResolvedValue({
    cv: CVS[0].parsed_data, verification_required: [], optimization_summary: [],
  })
  ;(atsPdf as Mock).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  renderWithIntl(<AtsPage />)
  await screen.findByLabelText('CV')
  await userEvent.click(screen.getByRole('button', { name: "ATS'ye Çevir" }))
  await waitFor(() => expect(downloadBlob).toHaveBeenCalled())
  expect(downloadBlob).toHaveBeenCalledWith(expect.anything(), 'Ada_ATSCV.pdf')
  expect(insertCv).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
    is_ats: true, source_cv_id: 'c2',
  }))
  expect(await screen.findByText(/Dönüştürüldü/)).toBeInTheDocument()
})

it('shows the empty-CV state and hides the form when there are no CVs', async () => {
  ;(listCvs as Mock).mockResolvedValueOnce([])
  renderWithIntl(<AtsPage />)
  expect(await screen.findByText(/Henüz CV'niz yok/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: "ATS'ye Çevir" })).not.toBeInTheDocument()
})

it('shows the verification and edit-summary panels after converting', async () => {
  ;(atsRewrite as Mock).mockResolvedValue({
    cv: CVS[0].parsed_data,
    verification_required: ['Confirm the end date of the Developer role.'],
    optimization_summary: ['Grouped skills by category.'],
  })
  ;(atsPdf as Mock).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  renderWithIntl(<AtsPage />)
  await screen.findByLabelText('CV')
  await userEvent.click(screen.getByRole('button', { name: "ATS'ye Çevir" }))
  expect(await screen.findByText('Confirm the end date of the Developer role.')).toBeInTheDocument()
  expect(screen.getByText('Grouped skills by category.')).toBeInTheDocument()
})

it('shows no panels when both lists are empty', async () => {
  ;(atsRewrite as Mock).mockResolvedValue({
    cv: CVS[0].parsed_data, verification_required: [], optimization_summary: [],
  })
  ;(atsPdf as Mock).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  renderWithIntl(<AtsPage />)
  await screen.findByLabelText('CV')
  await userEvent.click(screen.getByRole('button', { name: "ATS'ye Çevir" }))
  expect(await screen.findByText(/Dönüştürüldü/)).toBeInTheDocument()
  expect(screen.queryByTestId('ats-verification')).not.toBeInTheDocument()
  expect(screen.queryByTestId('ats-summary')).not.toBeInTheDocument()
})
