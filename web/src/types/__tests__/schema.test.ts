import fs from 'node:fs'
import path from 'node:path'
import type { CvRow, EvaluationRow, JobPostingRow, NewCv } from '@/types/db'
import type { CVData } from '@/types/api'

const sql = () =>
  fs.readFileSync(path.resolve(process.cwd(), '../supabase/migrations/0001_init.sql'), 'utf-8')

it('migration enables RLS on all four tables', () => {
  const matches = sql().match(/enable row level security/g) ?? []
  expect(matches.length).toBeGreaterThanOrEqual(4)
})

it('migration enforces one evaluation per cv+job pair', () => {
  expect(sql()).toMatch(/unique\s*\(cv_id,\s*job_id\)/)
})

it('row types accept well-formed values', () => {
  const cv: CVData = {
    full_name: 'Ada Lovelace', email: null, phone: null, location: null, summary: null,
    experiences: [], education: [], skills: ['Python'], languages: [], certifications: [],
  }
  const row: NewCv = { user_id: 'u1', file_path: 'u1/a.pdf', parsed_data: cv, is_ats: false, source_cv_id: null }
  const full: CvRow = { ...row, id: 'c1', created_at: '2026-07-12T00:00:00Z' }
  const job: JobPostingRow = {
    id: 'j1', user_id: 'u1', url: null, title: 'Dev', company: null,
    description: 'desc', fetch_method: 'manual', created_at: '2026-07-12T00:00:00Z',
  }
  const ev: EvaluationRow = {
    id: 'e1', cv_id: full.id, job_id: job.id, percent: 78, stars: 4,
    strengths: [], gaps: [], suggestions: [], created_at: '2026-07-12T00:00:00Z',
  }
  expect(ev.stars).toBe(4)
})
