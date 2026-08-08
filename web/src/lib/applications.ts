import type { SupabaseClient } from '@supabase/supabase-js'
import type { CVData, FieldAnswer, FormField } from '@/types/api'
import { insertApplication, insertCv } from '@/lib/db'

export async function saveApplication(sb: SupabaseClient, args: {
  userId: string
  sourceCvId: string
  optimizedCv: CVData
  pdf: Blob
  url: string
  jobText: string
  coverLetter: string
  form: FormField[]
  answers: FieldAnswer[]
  changes: string[]
  status: 'submitted' | 'delivered' | 'failed'
  // Read off the posting during /apply/prepare. Null when it did not say —
  // the row is still worth writing, it just cannot name itself.
  company?: string | null
  title?: string | null
}): Promise<void> {
  const path = `${args.userId}/${crypto.randomUUID()}-optimized.pdf`
  const { error } = await sb.storage.from('cvs').upload(path, args.pdf, { contentType: 'application/pdf' })
  if (error) throw error

  const optimized = await insertCv(sb, {
    user_id: args.userId, file_path: path, parsed_data: args.optimizedCv,
    is_ats: false, source_cv_id: args.sourceCvId,
  })
  await insertApplication(sb, {
    user_id: args.userId, cv_id: args.sourceCvId, optimized_cv_id: optimized.id,
    url: args.url, job_text: args.jobText, cover_letter: args.coverLetter,
    qa: { form: args.form, answers: args.answers }, changes: args.changes, status: args.status,
    company: args.company ?? null, title: args.title ?? null,
  })
}
