// Mirrors api/app/schemas.py (Plan 1). Keep in sync by hand.

export interface Experience {
  title: string
  company: string
  location?: string | null
  start_date: string | null
  end_date: string | null
  /** Legacy paragraph form; rows written before the ATS engine use this. */
  description: string | null
  /** Set by the ATS rewrite; absent on older rows. */
  bullets?: string[]
}

export interface Education {
  degree: string | null
  school: string
  location?: string | null
  start_date?: string | null
  year: string | null
  details?: string[]
}

export interface Project {
  name: string
  kind: string | null
  technologies: string[]
  bullets: string[]
}

export interface Certification {
  name: string
  issuer: string | null
  date: string | null
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
  /** Profile URLs; application forms ask for these constantly. Absent on older rows. */
  linkedin?: string | null
  github?: string | null
  website?: string | null
  summary: string | null
  experiences: Experience[]
  education: Education[]
  skills: string[]
  /** Set by the ATS rewrite; absent on raw parses and older rows. */
  skill_groups?: SkillGroup[]
  /** Absent on older rows. */
  projects?: Project[]
  achievements?: string[]
  languages: string[]
  /**
   * The API coerces plain strings into Certification objects, but rows read
   * straight out of Supabase were written before that existed and still hold
   * strings. Every consumer must handle both.
   */
  certifications: (Certification | string)[]
}

export interface AtsRewriteResult {
  cv: CVData
  verification_required: string[]
  optimization_summary: string[]
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
  /** Absent on responses from an API older than the ATS engine. */
  verification_required?: string[]
  cover_letter: string | null
  answers: FieldAnswer[]
  job_text: string
  // Read off the posting during prepare; null when it does not name them.
  company: string | null
  title: string | null
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

export type AssistNoFormReason =
  'login_wall' | 'captcha' | 'no_controls' | 'unsupported' | 'browser_closed' | 'blocked'

export type AssistFillResult =
  | {
      status: 'filled'
      filled: { label: string; value: string }[]
      // fields a custom widget silently refused; the user completes these by hand
      unfilled?: { label: string; reason: string }[]
      field_count: number
      screenshot: string
    }
  | { status: 'no_form'; reason?: AssistNoFormReason }
