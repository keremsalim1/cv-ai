'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Mail } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { getCv } from '@/lib/db'
import type { CvRow } from '@/types/db'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-5">
      <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
        {title}
      </h2>
      <div className="type-body mt-3 text-foreground">{children}</div>
    </section>
  )
}

export default function CvDetailPage() {
  const t = useTranslations()
  const { id } = useParams<{ id: string }>()
  const [supabase] = useState(createClient)
  const [cv, setCv] = useState<CvRow | null>(null)

  const load = useCallback(async () => {
    setCv(await getCv(supabase, id))
  }, [supabase, id])

  useEffect(() => {
    load()
  }, [load])

  if (!cv) {
    return (
      <main className="mx-auto w-full max-w-3xl px-5 py-16 sm:px-8">
        <div className="h-40 animate-pulse rounded-2xl bg-muted/70" aria-hidden />
        <span className="sr-only">{t('common.loading')}</span>
      </main>
    )
  }

  const d = cv.parsed_data
  const contact = [d.email, d.phone, d.location].filter(Boolean).join(' · ')

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-16 sm:px-8">
      {/* Header */}
      <div className="min-w-0">
        <h1 className="type-title text-ink">
          {d.full_name}
        </h1>
        {contact && (
          <p className="type-ui mt-1.5 flex items-center gap-1.5 text-muted-foreground">
            <Mail aria-hidden className="size-3.5" />
            {contact}
          </p>
        )}
      </div>

      {/* Document panel — reads as an actual CV, not a stack of identical cards */}
      <article className="grain flex flex-col gap-6 rounded-2xl bg-card p-7 shadow-e1 ring-1 ring-foreground/[0.07] sm:p-9">
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
                    <p className="type-ui mt-1 text-muted-foreground">{e.description}</p>
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
