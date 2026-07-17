'use client'
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'

/** Fake-determinate progress bar for LLM-backed waits (scoring, ATS
 *  conversion): fills fast at first, then eases toward 95% and holds
 *  until the operation completes and the component unmounts. Driven by
 *  JS state, not CSS animation, so it moves even with reduced motion.
 *  Past 60s a high-demand notice appears. */
export function ProgressBar({ label }: { label: string }) {
  const t = useTranslations('common')
  const [pct, setPct] = useState(3)
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    const start = Date.now()
    const timer = setInterval(() => {
      const elapsed = (Date.now() - start) / 1000
      setPct(3 + 92 * (1 - Math.exp(-elapsed / 25)))
      if (elapsed > 60) setSlow(true)
    }, 400)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="flex flex-col gap-1.5" role="status" aria-live="polite">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500 ease-linear"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="font-mono text-xs tracking-wide text-muted-foreground">{label}</p>
      {slow && (
        <p className="text-xs leading-snug text-warning-foreground">{t('longWait')}</p>
      )}
    </div>
  )
}
