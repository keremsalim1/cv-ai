import { createClient } from '@/lib/supabase/client'
import type { AssistFillResult, CVData, EvaluationResult, FieldAnswer, JobCriteria, JobFetchResult, PrepareResult, SubmitResult } from '@/types/api'

export class ApiError extends Error {
  constructor(public code: string, public status: number) {
    super(code)
    this.name = 'ApiError'
  }
}

function apiUrl(path: string): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + path
}

async function authHeaders(): Promise<Record<string, string>> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new ApiError('NOT_AUTHENTICATED', 401)
  return { Authorization: `Bearer ${session.access_token}` }
}

async function ensureOk(res: Response): Promise<Response> {
  if (res.ok) return res
  let code = 'UNKNOWN'
  try {
    const body = await res.json()
    if (typeof body?.detail?.code === 'string') code = body.detail.code
  } catch {
    // non-JSON error body
  }
  throw new ApiError(code, res.status)
}

export async function parseCv(file: File): Promise<CVData> {
  const form = new FormData()
  form.append('file', file)
  const res = await ensureOk(
    await fetch(apiUrl('/cv/parse'), { method: 'POST', headers: await authHeaders(), body: form })
  )
  return (await res.json()).cv
}

export async function fetchJob(input: { url?: string; text?: string }): Promise<JobFetchResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/job/fetch'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  )
  return res.json()
}

export async function scoreCv(cv: CVData, job: JobCriteria): Promise<EvaluationResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/score'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, job }),
    })
  )
  return res.json()
}

export async function atsRewrite(cv: CVData, language: string): Promise<CVData> {
  const res = await ensureOk(
    await fetch(apiUrl('/ats/rewrite'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, language }),
    })
  )
  return (await res.json()).cv
}

export async function atsPdf(cv: CVData, language: string): Promise<Blob> {
  const res = await ensureOk(
    await fetch(apiUrl('/ats/pdf'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, language }),
    })
  )
  return res.blob()
}

export async function applyPrepare(
  cv: CVData, url: string, language: string, headed = false
): Promise<PrepareResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/prepare'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, url, language, headed }),
    })
  )
  return res.json()
}

export async function applySubmit(
  cv: CVData, url: string, language: string, answers: FieldAnswer[], headed = false
): Promise<SubmitResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/submit'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, url, language, answers, headed }),
    })
  )
  return res.json()
}

export async function assistStart(url: string): Promise<{ session_id: string }> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/assist/start'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
  )
  return res.json()
}

export async function assistFill(
  sessionId: string, cv: CVData, language: string
): Promise<AssistFillResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/assist/fill'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, cv, language }),
    })
  )
  return res.json()
}

export async function assistClose(sessionId: string): Promise<void> {
  await ensureOk(
    await fetch(apiUrl('/apply/assist/close'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    })
  )
}

export interface InboxStatus {
  connected: boolean
  email: string | null
  last_synced_at: string | null
  status: 'active' | 'revoked' | 'error' | null
}

export interface SyncReport {
  scanned: number
  classified: number
  created: number
  updated: {
    application_id: string
    company: string | null
    from_stage: string
    to_stage: string
  }[]
  partial: boolean
}

export async function inboxStatus(): Promise<InboxStatus> {
  const res = await ensureOk(
    await fetch(apiUrl('/inbox/status'), { headers: await authHeaders() })
  )
  return res.json()
}

export async function inboxSync(): Promise<SyncReport> {
  const res = await ensureOk(
    await fetch(apiUrl('/inbox/sync'), { method: 'POST', headers: await authHeaders() })
  )
  return res.json()
}

export async function inboxConnect(
  code: string, redirectUri: string
): Promise<{ connected: boolean; email: string }> {
  const res = await ensureOk(
    await fetch(apiUrl('/inbox/connect'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
    })
  )
  return res.json()
}

export async function inboxDisconnect(): Promise<void> {
  await ensureOk(
    await fetch(apiUrl('/inbox/connect'), { method: 'DELETE', headers: await authHeaders() })
  )
}
