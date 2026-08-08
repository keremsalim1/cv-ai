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

export type ApplicationStage = 'received' | 'in_review' | 'interview' | 'offer' | 'rejected'

export interface ApplicationRow {
  id: string
  user_id: string
  cv_id: string | null
  optimized_cv_id: string | null
  url: string
  job_text: string | null
  cover_letter: string | null
  qa: unknown
  changes: string[]
  status: 'submitted' | 'delivered' | 'failed' | 'external'
  company: string | null
  title: string | null
  stage: ApplicationStage
  stage_updated_at: string | null
  source: 'assisted' | 'email'
  created_at: string
}
export type NewApplication = Omit<
  ApplicationRow, 'id' | 'created_at' | 'company' | 'title' | 'stage' | 'stage_updated_at' | 'source'
> & Partial<Pick<ApplicationRow, 'company' | 'title' | 'stage' | 'source'>>

export interface ApplicationEventRow {
  id: string
  user_id: string
  application_id: string
  source: 'email'
  message_id: string
  thread_id: string | null
  from_address: string | null
  subject: string | null
  received_at: string | null
  detected_stage: ApplicationStage | null
  confidence: number | null
  evidence: string | null
  created_at: string
}

export interface EmailConnectionStatus {
  user_id: string
  email_address: string
  last_synced_at: string | null
  status: 'active' | 'revoked' | 'error'
}
