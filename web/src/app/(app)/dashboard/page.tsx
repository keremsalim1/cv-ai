'use client'
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Upload, FileText, AlertCircle } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { deleteCv, insertCv, listCvs } from '@/lib/db'
import { ApiError, parseCv } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { MAX_FILE_SIZE } from '@/lib/constants'
import type { CvRow } from '@/types/db'
import { CvCard } from '@/components/CvCard'

export default function DashboardPage() {
  const t = useTranslations()
  const router = useRouter()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      router.replace('/login')
      return
    }
    setCvs(await listCvs(supabase))
  }, [supabase, router])

  useEffect(() => {
    load()
  }, [load])

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setError(null)
    if (file.type !== 'application/pdf') {
      setError(t('errors.INVALID_PDF'))
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      setError(t('errors.FILE_TOO_LARGE'))
      return
    }
    setBusy(true)
    try {
      const parsed = await parseCv(file) // parse first: a rejected PDF leaves no orphan file
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new ApiError('NOT_AUTHENTICATED', 401)
      const path = `${user.id}/${crypto.randomUUID()}.pdf`
      const { error: upErr } = await supabase.storage.from('cvs').upload(path, file)
      if (upErr) throw upErr
      await insertCv(supabase, {
        user_id: user.id, file_path: path, parsed_data: parsed, is_ats: false, source_cv_id: null,
      })
      await load()
    } catch (err) {
      setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
    } finally {
      setBusy(false)
    }
  }

  async function onDelete(cv: CvRow) {
    if (!window.confirm(t('dashboard.deleteConfirm'))) return
    setError(null)
    try {
      await deleteCv(supabase, cv)
      await load()
    } catch {
      setError(t('errors.UNKNOWN'))
    }
  }

  const count = cvs?.length ?? 0

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-5 py-12 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
            {t('dashboard.title')}
          </h1>
          {cvs !== null && count > 0 && (
            <p className="mt-1 font-mono text-xs tracking-wide text-muted-foreground">
              {count} {count === 1 ? 'CV' : 'CV'}
            </p>
          )}
        </div>

        <label
          className={`inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 transition-all hover:-translate-y-0.5 hover:bg-primary/90 ${busy ? 'pointer-events-none opacity-70' : ''}`}
        >
          <Upload aria-hidden className="size-4" />
          {busy ? t('dashboard.uploading') : t('dashboard.upload')}
          <input
            type="file"
            accept="application/pdf"
            className="sr-only"
            aria-label={t('dashboard.upload')}
            disabled={busy}
            onChange={onFile}
          />
        </label>
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
          <AlertCircle aria-hidden className="size-4 shrink-0" />
          {error}
        </p>
      )}

      {cvs === null ? (
        <div className="flex flex-col gap-3" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-[68px] animate-pulse rounded-xl bg-muted/70" />
          ))}
        </div>
      ) : count === 0 ? (
        <div className="grain flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <span className="grid size-14 place-items-center rounded-full bg-primary/8 text-primary ring-1 ring-primary/12">
            <FileText aria-hidden className="size-6" />
          </span>
          <p className="max-w-xs text-[15px] leading-relaxed text-muted-foreground">
            {t('dashboard.empty')}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {cvs.map((cv) => <CvCard key={cv.id} cv={cv} onDelete={() => onDelete(cv)} />)}
        </div>
      )}
    </main>
  )
}
