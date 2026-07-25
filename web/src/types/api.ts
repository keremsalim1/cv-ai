// Mirrors api/app/schemas.py (Plan 1). Keep in sync by hand.

export interface Experience {
  title: string
  company: string
  start_date: string | null
  end_date: string | null
  description: string | null
}

export interface Education {
  degree: string | null
  school: string
  year: string | null
}

export interface SkillGroup {
  name: string
  skills: string[]
}

export interface CVData {
  full_name: string
  title?: string | null
  email: string | null
  phone: string | null
  location: string | null
  summary: string | null
  experiences: Experience[]
  education: Education[]
  skills: string[]
  /** Set by the ATS rewrite; absent on raw parses and older rows. */
  skill_groups?: SkillGroup[]
  languages: string[]
  certifications: string[]
}

export interface JobCriteria {
  title: string
  company: string | null
  requirements: string[]
  skills: string[]
}

export interface EvaluationResult {
  percent: number
  stars: number
  strengths: string[]
  gaps: string[]
  suggestions: string[]
}

export interface JobFetchResult {
  criteria: JobCriteria
  description: string
  fetch_method: 'url' | 'manual'
}

export type FieldType = 'text' | 'textarea' | 'select' | 'radio' | 'checkbox' | 'file'

export interface FormField {
  id: string
  selector: string
  label: string
  type: FieldType
  options: string[]
  option_selectors: string[]
  required: boolean
}

export interface FieldAnswer {
  field_id: string
  value: string
}

// ready/captcha/form_not_found share this payload; `status` only gates auto-submit.
export interface OptimizedPayload {
  form: FormField[]
  cv: CVData
  changes: string[]
  cover_letter: string | null
  answers: FieldAnswer[]
  job_text: string
}

export type PrepareResult =
  | ({ status: 'ready' } & OptimizedPayload)
  | ({ status: 'captcha' } & OptimizedPayload)
  | ({ status: 'form_not_found' } & OptimizedPayload)
  | { status: 'login_required' }

export type SubmitResult =
  | { status: 'submitted'; screenshot: string }
  | { status: 'failed'; reason: string }
  | { status: 'login_required' }
  | { status: 'captcha' }

export type AssistFillResult =
  | { status: 'filled'; filled: { label: string; value: string }[]; field_count: number; screenshot: string }
  | { status: 'no_form' }
