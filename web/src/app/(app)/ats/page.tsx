'use client'
import { Suspense, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Download, AlertCircle, CheckCircle2, FileOutput } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { insertCv, listCvs } from '@/lib/db'
import { ApiError, atsPdf, atsRewrite } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { downloadBlob } from '@/lib/download'
import { cn } from '@/lib/utils'
import type { CvRow } from '@/types/db'
import { CvSelect } from '@/components/CvSelect'
import { ProgressTimer } from '@/components/ProgressTimer'
import { Button, buttonVariants } from '@/components/ui/button'

function AtsPageInner() {
  const t = useTranslations()
  const locale = useLocale()
  const router = useRouter()
  const params = useSearchParams()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [atsLang, setAtsLang] = useState<'tr' | 'en'>(locale === 'en' ? 'en' : 'tr')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      router.replace('/login')
      return
    }
    const rows = await listCvs(supabase)
    setCvs(rows)
    const fromQuery = params.get('cv')
    setSelected(fromQuery && rows.some((r) => r.id === fromQuery) ? fromQuery : rows[0]?.id ?? '')
  }, [supabase, router, params])

  useEffect(() => {
    load()
  }, [load])

  async function convert() {
    const cv = cvs?.find((c) => c.id === selected)
    if (!cv) return
    setError(null)
    setDone(false)
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
      const safeName = rewritten.full_name.trim()
        .replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, '_')
      downloadBlob(pdf, `${safeName}_ATSCV.pdf`)
      setDone(true)
    } catch (err) {
      setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
    } finally {
      setBusy(false)
    }
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
          <FileOutput aria-hidden className="size-3.5" />
          {t('ats.title')}
        </p>
        <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
          {t('ats.intro')}
        </p>
      </header>

      {cvs.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <p className="max-w-xs text-[15px] leading-relaxed text-muted-foreground">
            {t('common.noCvs')}
          </p>
          <Link href="/dashboard" className={cn(buttonVariants({ size: 'sm' }))}>
            {t('nav.dashboard')}
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
          <CvSelect cvs={cvs} value={selected} onChange={(id) => { setSelected(id); setDone(false); setError(null) }} />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            {t('ats.language')}
            <select
              value={atsLang}
              onChange={(e) => setAtsLang(e.target.value as 'tr' | 'en')}
              className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground transition-all outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <option value="tr">Türkçe</option>
              <option value="en">English</option>
            </select>
          </label>
          {error && (
            <p className="flex items-center gap-2 rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
              <AlertCircle aria-hidden className="size-4 shrink-0" />
              {error}
            </p>
          )}
          {done && (
            <p className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
              <CheckCircle2 aria-hidden className="size-4 shrink-0" />
              {t('ats.done')}
            </p>
          )}
          {busy && <ProgressTimer label={t('ats.converting')} />}
          <Button onClick={convert} disabled={busy || !selected} className="h-11 gap-1.5 text-base">
            <Download aria-hidden className="size-4" />
            {busy ? t('ats.converting') : t('ats.convert')}
          </Button>
        </div>
      )}
    </main>
  )
}

export default function AtsPage() {
  return (
    <Suspense fallback={null}>
      <AtsPageInner />
    </Suspense>
  )
}
