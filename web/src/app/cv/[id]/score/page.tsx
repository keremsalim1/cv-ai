'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import {
  findEvaluation, findJobByUrl, getCv, insertEvaluation, insertJob,
} from '@/lib/db'
import { ApiError, fetchJob, scoreCv } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import type { CvRow, EvaluationRow } from '@/types/db'
import { StarRating } from '@/components/StarRating'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

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
      if (err instanceof ApiError && err.code === 'FETCH_FAILED') {
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
    return <main className="px-4 py-10 text-sm text-muted-foreground">{t('common.loading')}</main>
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-10">
      <h1 className="text-2xl font-semibold">{t('score.title')} — {cv.parsed_data.full_name}</h1>

      <form onSubmit={run} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('score.urlLabel')}
          <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        {showPaste && (
          <label className="flex flex-col gap-1 text-sm">
            {t('score.pasteLabel')}
            <Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
        )}
        {error && <p className="text-sm text-amber-700">{error}</p>}
        <Button type="submit" disabled={busy}>
          {busy ? t('score.scoring') : t('score.scoreButton')}
        </Button>
      </form>

      {result && (
        <Card className="flex flex-col gap-3 p-6">
          {cached && <p className="text-sm text-muted-foreground">{t('score.cached')}</p>}
          <div className="flex items-center gap-3">
            <StarRating stars={result.stars} />
            <span className="text-2xl font-bold">%{result.percent}</span>
          </div>
          <section>
            <h2 className="font-medium">{t('score.strengths')}</h2>
            <ul className="list-disc pl-5 text-sm">
              {result.strengths.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">{t('score.gaps')}</h2>
            <ul className="list-disc pl-5 text-sm">
              {result.gaps.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">{t('score.suggestions')}</h2>
            <ul className="list-disc pl-5 text-sm">
              {result.suggestions.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
        </Card>
      )}
    </main>
  )
}
