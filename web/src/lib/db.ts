import type { SupabaseClient } from '@supabase/supabase-js'
import type {
  ApplicationRow, CvRow, EvaluationRow, JobPostingRow, NewApplication, NewCv, NewEvaluation, NewJobPosting,
} from '@/types/db'

export async function listCvs(sb: SupabaseClient): Promise<CvRow[]> {
  const { data, error } = await sb.from('cvs').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return (data ?? []) as CvRow[]
}

export async function getCv(sb: SupabaseClient, id: string): Promise<CvRow | null> {
  const { data, error } = await sb.from('cvs').select('*').eq('id', id).maybeSingle()
  if (error) throw error
  return data as CvRow | null
}

export async function deleteCv(sb: SupabaseClient, cv: CvRow): Promise<void> {
  const { error } = await sb.from('cvs').delete().eq('id', cv.id)
  if (error) throw error
  // Row is gone; a failed storage cleanup only leaves an orphan file
  await sb.storage.from('cvs').remove([cv.file_path])
}

export async function insertCv(sb: SupabaseClient, row: NewCv): Promise<CvRow> {
  const { data, error } = await sb.from('cvs').insert(row).select().single()
  if (error) throw error
  return data as CvRow
}

export async function findJobByUrl(sb: SupabaseClient, url: string): Promise<JobPostingRow | null> {
  const { data, error } = await sb.from('job_postings').select('*').eq('url', url).maybeSingle()
  if (error) throw error
  return data as JobPostingRow | null
}

export async function insertJob(sb: SupabaseClient, row: NewJobPosting): Promise<JobPostingRow> {
  const { data, error } = await sb.from('job_postings').insert(row).select().single()
  if (error) throw error
  return data as JobPostingRow
}

export async function findEvaluation(
  sb: SupabaseClient, cvId: string, jobId: string
): Promise<EvaluationRow | null> {
  const { data, error } = await sb
    .from('evaluations').select('*').eq('cv_id', cvId).eq('job_id', jobId).maybeSingle()
  if (error) throw error
  return data as EvaluationRow | null
}

export async function insertEvaluation(
  sb: SupabaseClient, row: NewEvaluation
): Promise<EvaluationRow> {
  const { data, error } = await sb.from('evaluations').insert(row).select().single()
  if (error) throw error
  return data as EvaluationRow
}

export async function listApplications(sb: SupabaseClient): Promise<ApplicationRow[]> {
  const { data, error } = await sb
    .from('applications').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return (data ?? []) as ApplicationRow[]
}

export async function insertApplication(
  sb: SupabaseClient, row: NewApplication
): Promise<ApplicationRow> {
  const { data, error } = await sb.from('applications').insert(row).select().single()
  if (error) throw error
  return data as ApplicationRow
}
