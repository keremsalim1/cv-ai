'use client'
import { useTranslations } from 'next-intl'
import { Wand2, CheckCircle2, Flag } from 'lucide-react'
import type { AssistFillResult, AssistNoFormReason } from '@/types/api'
import { Button } from '@/components/ui/button'
import { ProgressBar } from '@/components/ProgressBar'

const REASON_KEYS: Record<AssistNoFormReason, string> = {
  login_wall: 'assistReasonLoginWall',
  captcha: 'assistReasonCaptcha',
  no_controls: 'assistReasonNoControls',
  unsupported: 'assistReasonUnsupported',
  browser_closed: 'assistReasonBrowserClosed',
}

export function AssistScreen({ result, busy, onFill, onFinish }: {
  result: AssistFillResult | null
  busy: boolean
  onFill: () => void
  onFinish: () => void
}) {
  const t = useTranslations('optimize')
  return (
    <div className="flex flex-col gap-6">
      <p className="rounded-lg bg-muted px-4 py-3 text-sm leading-relaxed text-muted-foreground">
        {t('assistIntro')}
      </p>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onFill} disabled={busy} className="h-11 gap-1.5 text-base">
          <Wand2 aria-hidden className="size-4" />
          {t('assistFill')}
        </Button>
        <Button variant="outline" onClick={onFinish} disabled={busy} className="h-11 gap-1.5 text-base">
          <Flag aria-hidden className="size-4" />
          {t('assistFinish')}
        </Button>
      </div>

      {busy && <ProgressBar label={t('assistFilling')} />}

      {result?.status === 'no_form' && (
        <p className="rounded-lg bg-warning/10 px-4 py-3 text-sm text-warning">
          {t(REASON_KEYS[result.reason ?? 'no_controls'])}
        </p>
      )}

      {result?.status === 'filled' && (
        <section className="flex flex-col gap-3">
          <p className="flex items-center gap-2 text-sm font-medium text-success">
            <CheckCircle2 aria-hidden className="size-4 shrink-0" />
            {t('assistFilledCount', { count: result.field_count })}
          </p>
          {result.filled.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
              {result.filled.map((f, i) => (
                <li key={i}><span className="text-foreground">{f.label}:</span> {f.value}</li>
              ))}
            </ul>
          )}
          {result.unfilled && result.unfilled.length > 0 && (
            <div className="rounded-lg bg-warning/10 px-4 py-3 text-sm text-warning">
              <p>{t('assistUnfilled')}</p>
              <ul className="mt-1 flex flex-col gap-1">
                {result.unfilled.map((f, i) => <li key={i}>{f.label}</li>)}
              </ul>
            </div>
          )}
          <img src={`data:image/png;base64,${result.screenshot}`} alt={t('assistFilledCount', { count: result.field_count })}
            className="w-full rounded-xl border border-border" />
          <p className="text-sm leading-relaxed text-muted-foreground">{t('assistReviewNote')}</p>
        </section>
      )}
    </div>
  )
}
