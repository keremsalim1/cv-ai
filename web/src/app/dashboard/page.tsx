'use client'
import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { insertCv, listCvs } from '@/lib/db'
import { ApiError, parseCv } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { MAX_FILE_SIZE } from '@/lib/constants'
import type { CvRow } from '@/types/db'
import { CvCard } from '@/components/CvCard'

export default function DashboardPage() {
  const t = useTranslations()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setCvs(await listCvs(supabase))
  }, [supabase])

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

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('dashboard.title')}</h1>
        <label className="cursor-pointer rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
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
      {error && <p className="text-sm text-red-600">{error}</p>}
      {cvs === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : cvs.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('dashboard.empty')}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {cvs.map((cv) => <CvCard key={cv.id} cv={cv} />)}
        </div>
      )}
    </main>
  )
}
