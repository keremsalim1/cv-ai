'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { CheckCircle2, AlertTriangle, Info, Lightbulb, Sparkles } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import {
  findEvaluation, findJobByUrl, getCv, insertEvaluation, insertJob,
} from '@/lib/db'
import { ApiError, fetchJob, scoreCv } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import type { CvRow, EvaluationRow } from '@/types/db'
import { StarRating } from '@/components/StarRating'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

const BAND = {
  high: { text: 'text-success', bar: 'bg-success', ring: 'ring-success/20' },
  mid: { text: 'text-warning', bar: 'bg-warning', ring: 'ring-warning/25' },
  low: { text: 'text-destructive', bar: 'bg-destructive', ring: 'ring-destructive/20' },
}
function bandFor(pct: number) {
  return pct >= 75 ? BAND.high : pct >= 50 ? BAND.mid : BAND.low
}

export default function ScorePage() {
  const t = useTranslations()
  const { id } = useParams<{ id: string }>()
  const [supabase] = useState(createClient)
  const [cv, setCv] = useState<CvRow | null>(null)
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [showPaste, setShowPaste] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EvaluationRow | null>(null)
  const [cached, setCached] = useState(false)

  const load = useCallback(async () => {
    setCv(await getCv(supabase, id))
  }, [supabase, id])

  useEffect(() => {
    load()
  }, [load])

  async function run(e: React.FormEvent) {
    e.preventDefault()
    if (!cv) return
    setError(null)
    setResult(null)
    setCached(false)
    setBusy(true)
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new ApiError('NOT_AUTHENTICATED', 401)

      const useText = showPaste && text.trim().length > 0
      const fetched = await fetchJob(useText ? { text } : { url })

      let job = fetched.fetch_method === 'url' ? await findJobByUrl(supabase, url) : null
      if (!job) {
        job = await insertJob(supabase, {
          user_id: user.id,
          url: fetched.fetch_method === 'url' ? url : null,
          title: fetched.criteria.title,
          company: fetched.criteria.company,
          description: fetched.description,
          fetch_method: fetched.fetch_method,
        })
      }

      const existing = await findEvaluation(supabase, cv.id, job.id)
      if (existing) {
        setResult(existing)
        setCached(true)
        return
      }

      const ev = await scoreCv(cv.parsed_data, fetched.criteria)
      const row = await insertEvaluation(supabase, { cv_id: cv.id, job_id: job.id, ...ev })
      setResult(row)
    } catch (err) {
      if (err instanceof ApiError && (err.code === 'FETCH_FAILED' || err.code === 'JOB_PARSE_FAILED')) {
        setShowPaste(true)
        setError(t('score.pasteFallbackNotice'))
      } else {
        setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
      }
    } finally {
      setBusy(false)
    }
  }

  if (!cv) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 py-12 sm:px-8">
        <div className="h-40 animate-pulse rounded-2xl bg-muted/70" aria-hidden />
        <span className="sr-only">{t('common.loading')}</span>
      </main>
    )
  }

  const band = result ? bandFor(result.percent) : BAND.high

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-7 px-5 py-12 sm:px-8">
      <header>
        <p className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.18em] text-primary/80">
          <Sparkles aria-hidden className="size-3.5" />
          {t('score.title')}
        </p>
        <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-ink">
          {cv.parsed_data.full_name}
        </h1>
      </header>

      <form onSubmit={run} className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
        <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
          {t('score.urlLabel')}
          <Input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="h-11 text-base"
            placeholder="https://…"
          />
        </label>
        <p className="-mt-2 flex items-start gap-1.5 text-[13px] font-normal leading-snug text-muted-foreground">
          <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t('score.urlHint')}
        </p>
        {showPaste && (
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            {t('score.pasteLabel')}
            <Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} className="text-base" />
          </label>
        )}
        {error && (
          <p className="flex items-start gap-2 rounded-md bg-warning/10 px-3 py-2 text-sm text-warning-foreground">
            <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy} className="h-11 text-base">
          {busy ? t('score.scoring') : t('score.scoreButton')}
        </Button>
      </form>

      {result && (
        <div className="flex flex-col gap-5 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-3 motion-safe:duration-500">
          {cached && (
            <p className="text-center font-mono text-xs tracking-wide text-muted-foreground">
              {t('score.cached')}
            </p>
          )}

          {/* Score readout — the payoff */}
          <div className={`grain flex flex-col items-center gap-3 rounded-2xl bg-card px-6 py-9 text-center ring-1 ${band.ring}`}>
            <StarRating stars={result.stars} />
            <span className={`font-display text-7xl font-semibold leading-none ${band.text}`}>
              %{result.percent}
            </span>
            <div className="mt-1 h-1.5 w-48 max-w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${band.bar}`}
                style={{ width: `${result.percent}%` }}
              />
            </div>
          </div>

          {/* Reasons */}
          <div className="grid gap-4 sm:grid-cols-3">
            <ReasonBlock
              icon={<CheckCircle2 aria-hidden className="size-4 text-success" />}
              title={t('score.strengths')}
              items={result.strengths}
            />
            <ReasonBlock
              icon={<AlertTriangle aria-hidden className="size-4 text-warning" />}
              title={t('score.gaps')}
              items={result.gaps}
            />
            <ReasonBlock
              icon={<Lightbulb aria-hidden className="size-4 text-primary" />}
              title={t('score.suggestions')}
              items={result.suggestions}
            />
          </div>
        </div>
      )}
    </main>
  )
}

function ReasonBlock({
  icon, title, items,
}: { icon: React.ReactNode; title: string; items: string[] }) {
  return (
    <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        {icon}
        {title}
      </h2>
      <ul className="mt-2.5 flex flex-col gap-1.5 text-sm text-muted-foreground">
        {items.map((s) => (
          <li key={s} className="leading-snug">{s}</li>
        ))}
      </ul>
    </section>
  )
}
