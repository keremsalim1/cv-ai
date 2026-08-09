import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
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

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
  }),
}))

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
}))

import { getCv } from '@/lib/db'
import type { CVData } from '@/types/api'
import CvDetailPage from '@/app/(app)/cv/[id]/page'

function withParsedData(data: Partial<CVData>) {
  vi.mocked(getCv).mockResolvedValue({ ...ROW, parsed_data: { ...ROW.parsed_data, ...data } })
}

afterEach(() => vi.mocked(getCv).mockResolvedValue(ROW))

it('renders the parsed CV preview', async () => {
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
  expect(screen.getByText(/Dev — AEC/)).toBeInTheDocument()
  expect(screen.getByText('Python')).toBeInTheDocument()
})

it('renders projects, achievements and structured certifications', async () => {
  withParsedData({
    projects: [{ name: 'Bombe', kind: 'academic', technologies: ['Python'],
                 bullets: ['Cracked ciphers.'] }],
    achievements: ['Best paper award, 1843'],
    certifications: [{ name: 'AWS SAA', issuer: 'Amazon', date: 'Mar 2024' }],
  })
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByText('Bombe')).toBeInTheDocument()
  expect(screen.getByText('Cracked ciphers.')).toBeInTheDocument()
  expect(screen.getByText('Best paper award, 1843')).toBeInTheDocument()
  expect(screen.getByText('AWS SAA | Amazon | Mar 2024')).toBeInTheDocument()
})

it('still renders certifications stored as plain strings', async () => {
  withParsedData({ certifications: ['AWS SAA', 'Scrum Master'] })
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByText('AWS SAA')).toBeInTheDocument()
  expect(screen.getByText('Scrum Master')).toBeInTheDocument()
})

it('renders experience bullets when present', async () => {
  withParsedData({
    experiences: [{ title: 'Developer', company: 'Acme', location: 'İstanbul',
                    start_date: 'Oca 2024', end_date: 'Devam Ediyor',
                    description: null, bullets: ['Designed REST APIs.'] }],
  })
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByText('Designed REST APIs.')).toBeInTheDocument()
})
