'use client'
import { Suspense, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Send, AlertCircle, LogIn } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { listCvs } from '@/lib/db'
import { ApiError, applyPrepare, applySubmit, assistClose, assistFill, assistStart, atsPdf } from '@/lib/api'
import { saveApplication } from '@/lib/applications'
import { messageKeyForCode } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { CvRow } from '@/types/db'
import type { AssistFillResult, FieldAnswer, OptimizedPayload, PrepareResult } from '@/types/api'
import { CvSelect } from '@/components/CvSelect'
import { ProgressBar } from '@/components/ProgressBar'
import { ApprovalScreen } from '@/components/apply/ApprovalScreen'
import { AssistScreen } from '@/components/apply/AssistScreen'
import { ResultScreen } from '@/components/apply/ResultScreen'
import { RecentApplications } from '@/components/apply/RecentApplications'
import { Button, buttonVariants } from '@/components/ui/button'

type Step = 'form' | 'preparing' | 'login' | 'approve' | 'submitting' | 'assist' | 'result'
type ResultView = { mode: 'submitted' | 'delivered'; screenshot?: string; pdf: Blob; pdfName: string; coverLetter: string; answers: FieldAnswer[] }

function pdfName(fullName: string): string {
  const safe = fullName.trim().replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, '_') || 'CV'
  return `${safe}_OptimizedCV.pdf`
}

function OptimizePageInner() {
  const t = useTranslations()
  const locale = useLocale()
  const router = useRouter()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [selected, setSelected] = useState('')
  const [url, setUrl] = useState('')
  const [lang, setLang] = useState<'tr' | 'en'>(locale === 'en' ? 'en' : 'tr')
  const [step, setStep] = useState<Step>('form')
  const [preparingLabel, setPreparingLabel] = useState('optimize.preparing')
  const [payload, setPayload] = useState<(OptimizedPayload & { status: PrepareResult['status'] }) | null>(null)
  const [result, setResult] = useState<ResultView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [assistResult, setAssistResult] = useState<AssistFillResult | null>(null)
  const [assistBusy, setAssistBusy] = useState(false)

  const load = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { router.replace('/login'); return }
    setCvs(await listCvs(supabase))
  }, [supabase, router])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (cvs && cvs.length && !selected) setSelected(cvs[0].id) }, [cvs, selected])

  const showError = (err: unknown) =>
    setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))

  async function prepare(headed: boolean) {
    const cv = cvs?.find((c) => c.id === selected)
    if (!cv || !url.trim()) return
    setError(null)
    // headed retry means the user is signing in by hand — show the waiting copy.
    setPreparingLabel(headed ? 'optimize.loginWaiting' : 'optimize.preparing')
    setStep('preparing')
    try {
      const res = await applyPrepare(cv.parsed_data, url.trim(), lang, headed)
      if (res.status === 'login_required') { setStep('login'); return }
      setPayload(res)
      setStep('approve')
    } catch (err) {
      showError(err)
      setStep('form')
    }
  }

  async function finish(mode: 'submitted' | 'delivered', optimized: OptimizedPayload,
                        answers: FieldAnswer[], coverLetter: string, screenshot?: string) {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { router.replace('/login'); return }
    const pdf = await atsPdf(optimized.cv, lang)
    try {
      await saveApplication(supabase, {
        userId: user.id, sourceCvId: selected, optimizedCv: optimized.cv, pdf,
        url: url.trim(), jobText: optimized.job_text, coverLetter,
        form: optimized.form, answers, changes: optimized.changes,
        status: mode === 'submitted' ? 'submitted' : 'delivered',
      })
    } catch (err) {
      showError(err)
    }
    setResult({ mode, screenshot, pdf, pdfName: pdfName(optimized.cv.full_name), coverLetter, answers })
    setStep('result')
  }

  async function onSubmit(answers: FieldAnswer[], coverLetter: string) {
    if (!payload) return
    setError(null)
    setStep('submitting')
    try {
      const cv = cvs!.find((c) => c.id === selected)!
      const res = await applySubmit(cv.parsed_data, url.trim(), lang, answers)
      if (res.status === 'submitted') {
        await finish('submitted', payload, answers, coverLetter, res.screenshot)
      } else {
        // failed / login_required / captcha between prepare and submit → delivery
        await finish('delivered', payload, answers, coverLetter)
      }
    } catch (err) {
      showError(err)
      await finish('delivered', payload, answers, coverLetter)
    }
  }

  async function onDeliver(answers: FieldAnswer[], coverLetter: string) {
    if (payload) await finish('delivered', payload, answers, coverLetter)
  }

  async function beginAssist() {
    const cv = cvs?.find((c) => c.id === selected)
    if (!cv || !url.trim()) return
    // login-mode has no optimized payload; synthesize one from the selected CV
    if (!payload) {
      setPayload({ status: 'form_not_found', cv: cv.parsed_data, form: [],
        changes: [], cover_letter: '', answers: [], job_text: '' })
    }
    setError(null)
    setAssistResult(null)
    setStep('assist')
    setAssistBusy(true)
    try {
      const { session_id } = await assistStart(url.trim())
      setSessionId(session_id)
    } catch (err) {
      showError(err)
      setStep(payload ? 'approve' : 'login')
    } finally {
      setAssistBusy(false)
    }
  }

  async function doAssistFill() {
    if (!sessionId) return
    const cv = payload?.cv ?? cvs!.find((c) => c.id === selected)!.parsed_data
    setError(null)
    setAssistBusy(true)
    try {
      setAssistResult(await assistFill(sessionId, cv, lang))
    } catch (err) {
      showError(err)
    } finally {
      setAssistBusy(false)
    }
  }

  async function finishAssist() {
    if (sessionId) { try { await assistClose(sessionId) } catch { /* already gone */ } }
    if (payload) await finish('delivered', payload, [], payload.cover_letter ?? '')
  }

  if (!cvs) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 py-12 sm:px-8">
        <div className="h-40 animate-pulse rounded-2xl bg-muted/70" aria-hidden />
        <span className="sr-only">{t('common.loading')}</span>
      </main>
    )
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-7 px-5 py-12 sm:px-8">
      <header>
        <p className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.18em] text-primary/80">
          <Send aria-hidden className="size-3.5" />
          {t('optimize.title')}
        </p>
        <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted-foreground">{t('optimize.intro')}</p>
      </header>

      {error && (
        <p className="flex items-center gap-2 rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
          <AlertCircle aria-hidden className="size-4 shrink-0" />
          {error}
        </p>
      )}

      {cvs.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <p className="max-w-xs text-[15px] leading-relaxed text-muted-foreground">{t('common.noCvs')}</p>
          <Link href="/dashboard" className={cn(buttonVariants({ size: 'sm' }))}>{t('nav.dashboard')}</Link>
        </div>
      ) : step === 'form' ? (
        <>
        <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
          <CvSelect cvs={cvs} value={selected} onChange={setSelected} />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            {t('optimize.link')}
            <input
              type="url" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder={t('optimize.linkPlaceholder')}
              className="h-11 rounded-lg border border-border bg-background px-3 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            {t('optimize.language')}
            <select value={lang} onChange={(e) => setLang(e.target.value as 'tr' | 'en')}
              className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50">
              <option value="tr">Türkçe</option>
              <option value="en">English</option>
            </select>
          </label>
          <Button onClick={() => prepare(false)} disabled={!selected || !url.trim()} className="h-11 gap-1.5 text-base">
            <Send aria-hidden className="size-4" />
            {t('optimize.prepare')}
          </Button>
        </div>
        <RecentApplications supabase={supabase} />
        </>
      ) : step === 'preparing' ? (
        <ProgressBar label={t(preparingLabel)} />
      ) : step === 'login' ? (
        <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
          <h2 className="text-lg font-semibold text-foreground">{t('optimize.loginTitle')}</h2>
          <p className="text-[15px] leading-relaxed text-muted-foreground">{t('optimize.loginIntro')}</p>
          <Button onClick={() => prepare(true)} className="h-11 gap-1.5 text-base">
            <LogIn aria-hidden className="size-4" />
            {t('optimize.loginButton')}
          </Button>
          <Button variant="outline" onClick={beginAssist} className="h-11 gap-1.5 text-base">
            <LogIn aria-hidden className="size-4" />
            {t('optimize.assistCta')}
          </Button>
        </div>
      ) : step === 'submitting' ? (
        <ProgressBar label={t('optimize.submitting')} />
      ) : step === 'approve' && payload ? (
        <>
          <h1 className="text-xl font-semibold text-foreground">{t('optimize.approveTitle')}</h1>
          {payload.status !== 'ready' && (
            <p className="rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">{t('optimize.deliverModeNote')}</p>
          )}
          <ApprovalScreen payload={payload} canSubmit={payload.status === 'ready'}
            onSubmit={onSubmit} onDeliver={onDeliver}
            onAssist={payload.status === 'ready' ? undefined : beginAssist} />
        </>
      ) : step === 'assist' ? (
        <>
          <h1 className="text-xl font-semibold text-foreground">{t('optimize.assist')}</h1>
          {!sessionId ? (
            <ProgressBar label={t('optimize.assistStarting')} />
          ) : (
            <AssistScreen result={assistResult} busy={assistBusy}
              onFill={doAssistFill} onFinish={finishAssist} />
          )}
        </>
      ) : step === 'result' && result ? (
        <ResultScreen {...result} />
      ) : null}
    </main>
  )
}

export default function OptimizePage() {
  return (
    <Suspense fallback={null}>
      <OptimizePageInner />
    </Suspense>
  )
}
