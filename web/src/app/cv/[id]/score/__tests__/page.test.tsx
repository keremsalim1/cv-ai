import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow, EvaluationRow, JobPostingRow } from '@/types/db'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
  }),
}))

const ROW: CvRow = {
  id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
  created_at: '2026-07-12T00:00:00Z',
  parsed_data: {
    full_name: 'Ada', email: null, phone: null, location: null, summary: null,
    experiences: [], education: [], skills: ['Python'], languages: [], certifications: [],
  },
}

const JOB: JobPostingRow = {
  id: 'j1', user_id: 'u1', url: 'https://x.co/1', title: 'Dev', company: 'Acme',
  description: 'desc', fetch_method: 'url', created_at: '2026-07-12T00:00:00Z',
}

const EVAL: EvaluationRow = {
  id: 'e1', cv_id: 'c1', job_id: 'j1', percent: 78, stars: 4,
  strengths: ['Python'], gaps: ['SQL'], suggestions: ['Add projects'],
  created_at: '2026-07-12T00:00:00Z',
}

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
  findJobByUrl: vi.fn(async () => null),
  insertJob: vi.fn(async () => JOB),
  findEvaluation: vi.fn(async () => null),
  insertEvaluation: vi.fn(async () => EVAL),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, fetchJob: vi.fn(), scoreCv: vi.fn() }
})

import { findEvaluation, findJobByUrl, insertEvaluation, insertJob } from '@/lib/db'
import { ApiError, fetchJob, scoreCv } from '@/lib/api'
import ScorePage from '@/app/cv/[id]/score/page'

const FETCHED = {
  criteria: { title: 'Dev', company: 'Acme', requirements: ['Python'], skills: ['Python'] },
  description: 'desc', fetch_method: 'url' as const,
}

beforeEach(() => vi.clearAllMocks())

it('scores a URL posting and shows stars with reasons', async () => {
  ;(fetchJob as Mock).mockResolvedValue(FETCHED)
  ;(scoreCv as Mock).mockResolvedValue({
    percent: 78, stars: 4, strengths: ['Python'], gaps: ['SQL'], suggestions: ['Add projects'],
  })
  renderWithIntl(<ScorePage />)
  await userEvent.type(await screen.findByLabelText('İş ilanı bağlantısı'), 'https://x.co/1')
  await userEvent.click(screen.getByRole('button', { name: 'Skorla' }))
  expect(await screen.findByLabelText('4/5')).toBeInTheDocument()
  expect(screen.getByText('%78')).toBeInTheDocument()
  expect(screen.getByText('SQL')).toBeInTheDocument()
  expect(insertJob).toHaveBeenCalled()
  expect(insertEvaluation).toHaveBeenCalled()
})

it('returns the cached evaluation without calling /score again', async () => {
  ;(fetchJob as Mock).mockResolvedValue(FETCHED)
  ;(findJobByUrl as Mock).mockResolvedValue(JOB)
  ;(findEvaluation as Mock).mockResolvedValue(EVAL)
  renderWithIntl(<ScorePage />)
  await userEvent.type(await screen.findByLabelText('İş ilanı bağlantısı'), 'https://x.co/1')
  await userEvent.click(screen.getByRole('button', { name: 'Skorla' }))
  expect(await screen.findByLabelText('4/5')).toBeInTheDocument()
  expect(screen.getByText(/önceki sonuç/)).toBeInTheDocument()
  expect(scoreCv).not.toHaveBeenCalled()
  expect(insertEvaluation).not.toHaveBeenCalled()
})

it('falls back to paste mode when the fetch fails', async () => {
  ;(fetchJob as Mock).mockRejectedValueOnce(new ApiError('FETCH_FAILED', 422))
  renderWithIntl(<ScorePage />)
  await userEvent.type(await screen.findByLabelText('İş ilanı bağlantısı'), 'https://linkedin.com/x')
  await userEvent.click(screen.getByRole('button', { name: 'Skorla' }))
  expect(await screen.findByText(/yapıştırın/)).toBeInTheDocument()
  expect(screen.getByLabelText('İlan metni')).toBeInTheDocument()
})
