'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Download, Target, Mail, AlertCircle } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { getCv, insertCv } from '@/lib/db'
import { ApiError, atsPdf, atsRewrite } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { downloadBlob } from '@/lib/download'
import type { CvRow } from '@/types/db'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-5">
      <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
        {title}
      </h2>
      <div className="mt-3 text-[15px] leading-relaxed text-foreground">{children}</div>
    </section>
  )
}

export default function CvDetailPage() {
  const t = useTranslations()
  const locale = useLocale()
  const { id } = useParams<{ id: string }>()
  const [supabase] = useState(createClient)
  const [cv, setCv] = useState<CvRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [atsLang, setAtsLang] = useState<'tr' | 'en'>(locale === 'en' ? 'en' : 'tr')

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
      const rewritten = await atsRewrite(cv.parsed_data, atsLang)
      const pdf = await atsPdf(rewritten, atsLang)
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
    return (
      <main className="mx-auto w-full max-w-3xl px-5 py-12 sm:px-8">
        <div className="h-40 animate-pulse rounded-2xl bg-muted/70" aria-hidden />
        <span className="sr-only">{t('common.loading')}</span>
      </main>
    )
  }

  const d = cv.parsed_data
  const contact = [d.email, d.phone, d.location].filter(Boolean).join(' · ')

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-12 sm:px-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
            {d.full_name}
          </h1>
          {contact && (
            <p className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
              <Mail aria-hidden className="size-3.5" />
              {contact}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <label className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              {t('cv.atsLanguage')}:
            </span>
            <select
              value={atsLang}
              onChange={(e) => setAtsLang(e.target.value as 'tr' | 'en')}
              className="h-8 rounded-lg border border-border bg-background px-2.5 text-sm font-medium text-foreground transition-all outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <option value="tr">Türkçe</option>
              <option value="en">English</option>
            </select>
          </label>
          <Button onClick={convert} disabled={busy} className="gap-1.5">
            <Download aria-hidden className="size-4" />
            {busy ? t('cv.converting') : t('cv.convertAts')}
          </Button>
          <Link
            href={`/cv/${cv.id}/score`}
            className={cn(buttonVariants({ variant: 'outline' }), 'gap-1.5')}
          >
            <Target aria-hidden className="size-4" />
            {t('cv.scoreCta')}
          </Link>
        </div>
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
          <AlertCircle aria-hidden className="size-4 shrink-0" />
          {error}
        </p>
      )}

      {/* Document panel — reads as an actual CV, not a stack of identical cards */}
      <article className="grain flex flex-col gap-6 rounded-2xl bg-card p-7 ring-1 ring-foreground/10 sm:p-9">
        {d.summary && <Section title={t('cv.summary')}>{d.summary}</Section>}

        {d.experiences.length > 0 && (
          <Section title={t('cv.experience')}>
            <ul className="flex flex-col gap-4">
              {d.experiences.map((e, i) => (
                <li key={i}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <span className="font-medium text-ink">{e.title} — {e.company}</span>
                    {(e.start_date || e.end_date) && (
                      <span className="font-mono text-xs text-muted-foreground">
                        {e.start_date ?? ''} – {e.end_date ?? ''}
                      </span>
                    )}
                  </div>
                  {e.description && (
                    <p className="mt-1 text-sm text-muted-foreground">{e.description}</p>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {d.education.length > 0 && (
          <Section title={t('cv.education')}>
            <ul className="flex flex-col gap-1.5">
              {d.education.map((e, i) => (
                <li key={i}>
                  <span className="font-medium text-ink">{e.degree ?? e.school}</span>
                  {e.degree ? <> — {e.school}</> : ''}
                  {e.year ? <span className="text-muted-foreground"> ({e.year})</span> : ''}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {(d.skill_groups?.length || d.skills.length > 0) && (
          <Section title={t('cv.skills')}>
            {d.skill_groups?.length ? (
              <div className="flex flex-col gap-3">
                {d.skill_groups.map((g) => (
                  <div key={g.name}>
                    <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {g.name}
                    </p>
                    <ul className="flex flex-wrap gap-2">
                      {g.skills.map((s) => (
                        <li
                          key={s}
                          className="rounded-md bg-secondary px-2.5 py-1 text-[13px] font-medium text-secondary-foreground"
                        >
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {d.skills.map((s) => (
                  <li
                    key={s}
                    className="rounded-md bg-secondary px-2.5 py-1 text-[13px] font-medium text-secondary-foreground"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}

        {d.languages.length > 0 && (
          <Section title={t('cv.languages')}>{d.languages.join(' · ')}</Section>
        )}

        {d.certifications.length > 0 && (
          <Section title={t('cv.certifications')}>{d.certifications.join(' · ')}</Section>
        )}
      </article>
    </main>
  )
}
