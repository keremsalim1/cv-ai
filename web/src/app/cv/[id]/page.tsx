'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { getCv, insertCv } from '@/lib/db'
import { ApiError, atsPdf, atsRewrite } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { downloadBlob } from '@/lib/download'
import type { CvRow } from '@/types/db'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

export default function CvDetailPage() {
  const t = useTranslations()
  const locale = useLocale()
  const { id } = useParams<{ id: string }>()
  const [supabase] = useState(createClient)
  const [cv, setCv] = useState<CvRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setCv(await getCv(supabase, id))
  }, [supabase, id])

  useEffect(() => {
    load()
  }, [load])

  async function convert() {
    if (!cv) return
    setError(null)
    setBusy(true)
    try {
      const rewritten = await atsRewrite(cv.parsed_data, locale)
      const pdf = await atsPdf(rewritten, locale)
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new ApiError('NOT_AUTHENTICATED', 401)
      const path = `${user.id}/${crypto.randomUUID()}-ats.pdf`
      const { error: upErr } = await supabase.storage
        .from('cvs')
        .upload(path, pdf, { contentType: 'application/pdf' })
      if (upErr) throw upErr
      await insertCv(supabase, {
        user_id: user.id, file_path: path, parsed_data: rewritten,
        is_ats: true, source_cv_id: cv.id,
      })
      downloadBlob(pdf, 'cv-ats.pdf')
    } catch (err) {
      setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
    } finally {
      setBusy(false)
    }
  }

  if (!cv) {
    return <main className="px-4 py-10 text-sm text-muted-foreground">{t('common.loading')}</main>
  }

  const d = cv.parsed_data
  const contact = [d.email, d.phone, d.location].filter(Boolean).join(' | ')

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{d.full_name}</h1>
        <div className="flex gap-2">
          <Button onClick={convert} disabled={busy}>
            {busy ? t('cv.converting') : t('cv.convertAts')}
          </Button>
          {/* Base UI Button: use render (asChild is Radix-only) */}
          <Button variant="outline" render={<Link href={`/cv/${cv.id}/score`} />}>
            {t('cv.scoreCta')}
          </Button>
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {contact && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.contact')}</h2>
          <p className="text-sm">{contact}</p>
        </Card>
      )}
      {d.summary && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.summary')}</h2>
          <p className="text-sm">{d.summary}</p>
        </Card>
      )}
      {d.experiences.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.experience')}</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {d.experiences.map((e, i) => (
              <li key={i}>
                <span className="font-medium">{e.title} — {e.company}</span>
                {(e.start_date || e.end_date) && (
                  <span className="text-muted-foreground"> ({e.start_date ?? ''} - {e.end_date ?? ''})</span>
                )}
                {e.description && <p>{e.description}</p>}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {d.education.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.education')}</h2>
          <ul className="text-sm">
            {d.education.map((e, i) => (
              <li key={i}>{e.degree} — {e.school}{e.year ? ` (${e.year})` : ''}</li>
            ))}
          </ul>
        </Card>
      )}
      {d.skills.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.skills')}</h2>
          <ul className="flex flex-wrap gap-2 text-sm">
            {d.skills.map((s) => (
              <li key={s} className="rounded bg-muted px-2 py-0.5">{s}</li>
            ))}
          </ul>
        </Card>
      )}
      {d.languages.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.languages')}</h2>
          <p className="text-sm">{d.languages.join(', ')}</p>
        </Card>
      )}
      {d.certifications.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.certifications')}</h2>
          <p className="text-sm">{d.certifications.join(', ')}</p>
        </Card>
      )}
    </main>
  )
}
