import type { CVData } from './api'

export interface ProfileRow {
  id: string
  full_name: string | null
  language: 'tr' | 'en'
}

export interface CvRow {
  id: string
  user_id: string
  file_path: string
  parsed_data: CVData
  is_ats: boolean
  source_cv_id: string | null
  created_at: string
}
export type NewCv = Omit<CvRow, 'id' | 'created_at'>

export interface JobPostingRow {
  id: string
  user_id: string
  url: string | null
  title: string
  company: string | null
  description: string
  fetch_method: 'url' | 'manual'
  created_at: string
}
export type NewJobPosting = Omit<JobPostingRow, 'id' | 'created_at'>

export interface EvaluationRow {
  id: string
  cv_id: string
  job_id: string
  percent: number
  stars: number
  strengths: string[]
  gaps: string[]
  suggestions: string[]
  created_at: string
}
export type NewEvaluation = Omit<EvaluationRow, 'id' | 'created_at'>
