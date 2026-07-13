import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
}))

const upload = vi.fn(async () => ({ data: { path: 'p' }, error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

const ROW: CvRow = {
  id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
  created_at: '2026-07-12T00:00:00Z',
  parsed_data: {
    full_name: 'Ada Lovelace', email: 'ada@example.com', phone: null, location: 'London',
    summary: 'Engineer.', experiences: [{ title: 'Dev', company: 'AEC', start_date: '2020', end_date: '2024', description: null }],
    education: [], skills: ['Python'], languages: [], certifications: [],
  },
}

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
  insertCv: vi.fn(async () => ({ ...ROW, id: 'c2', is_ats: true })),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, atsRewrite: vi.fn(), atsPdf: vi.fn() }
})

vi.mock('@/lib/download', () => ({ downloadBlob: vi.fn() }))

import { insertCv } from '@/lib/db'
import { atsPdf, atsRewrite } from '@/lib/api'
import { downloadBlob } from '@/lib/download'
import CvDetailPage from '@/app/cv/[id]/page'

beforeEach(() => vi.clearAllMocks())

it('renders the parsed CV preview', async () => {
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
  expect(screen.getByText(/Dev — AEC/)).toBeInTheDocument()
  expect(screen.getByText('Python')).toBeInTheDocument()
})

it('converts to ATS: rewrite, pdf, storage, new row, download', async () => {
  ;(atsRewrite as Mock).mockResolvedValue(ROW.parsed_data)
  ;(atsPdf as Mock).mockResolvedValue(new Blob([new Uint8Array([1])], { type: 'application/pdf' }))
  renderWithIntl(<CvDetailPage />)
  await userEvent.click(await screen.findByRole('button', { name: "ATS'ye Dönüştür" }))
  await waitFor(() => expect(downloadBlob).toHaveBeenCalled())
  expect(atsRewrite).toHaveBeenCalledWith(ROW.parsed_data, 'tr')
  expect(atsPdf).toHaveBeenCalled()
  expect(upload).toHaveBeenCalled()
  const inserted = (insertCv as Mock).mock.calls[0][1]
  expect(inserted).toMatchObject({ is_ats: true, source_cv_id: 'c1', user_id: 'u1' })
})
