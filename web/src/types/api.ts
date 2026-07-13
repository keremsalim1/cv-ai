// Mirrors api/app/schemas.py (Plan 1). Keep in sync by hand.

export interface Experience {
  title: string
  company: string
  start_date: string | null
  end_date: string | null
  description: string | null
}

export interface Education {
  degree: string
  school: string
  year: string | null
}

export interface CVData {
  full_name: string
  email: string | null
  phone: string | null
  location: string | null
  summary: string | null
  experiences: Experience[]
  education: Education[]
  skills: string[]
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
