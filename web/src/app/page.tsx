'use client'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { ArrowRight, Sparkles, Upload, Target, FileCheck2 } from 'lucide-react'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function Home() {
  const t = useTranslations('landing')

  const steps = [
    { n: '01', icon: Upload, title: t('step1Title'), body: t('step1Body') },
    { n: '02', icon: Target, title: t('step2Title'), body: t('step2Body') },
    { n: '03', icon: FileCheck2, title: t('step3Title'), body: t('step3Body') },
  ]

  return (
    <main className="flex flex-col">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="oxblood-wash grain relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl items-center gap-14 px-5 py-16 sm:px-8 lg:grid-cols-[1.05fr_0.95fr]">
          {/* Copy */}
          <div className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-4 motion-safe:duration-700">
            <span className="type-meta inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/5 px-3 py-1 text-primary">
              <Sparkles aria-hidden className="size-3.5" />
              {t('badge')}
            </span>

            <h1 className="type-display mt-5 text-balance text-ink">
              CV&apos;nizi <span className="whitespace-nowrap italic text-primary">yapay zeka</span> ile işe hazırlayın
            </h1>

            <p className="type-body mt-5 max-w-md text-muted-foreground">
              {t('subtitle')}
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/register"
                className={cn(
                  buttonVariants({ size: 'lg' }),
                  'h-12 gap-2 px-6 text-base shadow-lg shadow-primary/20 transition-transform hover:-translate-y-0.5',
                )}
              >
                {t('cta')}
                <ArrowRight aria-hidden className="size-4" />
              </Link>
              <Link
                href="#nasil"
                className={cn(
                  buttonVariants({ variant: 'ghost', size: 'lg' }),
                  'h-12 px-4 text-base text-muted-foreground',
                )}
              >
                {t('howTitle')}
              </Link>
            </div>

            <p className="type-meta mt-5 text-muted-foreground">
              {t('ctaNote')}
            </p>
          </div>

          {/* Product artifact: an honest score readout — the one thing to remember */}
          <div className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-6 motion-safe:duration-1000">
            <ScoreArtifact
              role={t('demoRole')}
              match={t('demoMatch')}
              strength={t('demoStrength')}
              gap={t('demoGap')}
            />
          </div>
        </div>
        <div className="hairline mx-auto max-w-6xl" />
      </section>

      {/* ── How it works (a real, ordered sequence) ──────────── */}
      <section id="nasil" className="mx-auto w-full max-w-6xl scroll-mt-20 px-5 py-16 sm:px-8">
        <h2 className="max-w-xl font-display text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold tracking-tight text-ink">
          {t('howTitle')}
        </h2>

        <ol className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-3">
          {steps.map((s, i) => (
            <li key={s.n} className="relative flex flex-col">
              {i < steps.length - 1 && (
                <span
                  aria-hidden
                  className="absolute top-6 left-12 hidden h-px w-[calc(100%-2rem)] bg-gradient-to-r from-border to-transparent sm:block"
                />
              )}
              <div className="flex items-center gap-4">
                <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-primary/8 text-primary ring-1 ring-primary/15">
                  <s.icon aria-hidden className="size-5" />
                </span>
                <span className="font-mono text-sm text-primary/70">{s.n}</span>
              </div>
              <h3 className="mt-5 font-display text-xl font-semibold text-ink">{s.title}</h3>
              <p className="type-body mt-2 text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* ── Closing CTA band (oxblood drench) ────────────────── */}
      <section className="px-5 pb-16 sm:px-8">
        <div className="grain relative mx-auto flex max-w-6xl flex-col items-center gap-6 overflow-hidden rounded-3xl bg-primary px-6 py-16 text-center text-primary-foreground">
          <h2 className="max-w-lg font-display text-[clamp(1.8rem,3.5vw,2.8rem)] font-semibold leading-tight text-balance">
            {t('closingTitle')}
          </h2>
          <Link
            href="/register"
            className={cn(buttonVariants({ variant: 'secondary', size: 'lg' }), 'h-12 gap-2 px-6 text-base')}
          >
            {t('ctaClosing')}
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        </div>
      </section>
    </main>
  )
}

function ScoreArtifact({
  role, match, strength, gap,
}: { role: string; match: string; strength: string; gap: string }) {
  return (
    <div className="relative mx-auto max-w-sm">
      {/* soft cast shadow behind the card */}
      <div
        aria-hidden
        className="absolute -inset-4 -z-10 rounded-[2rem] bg-primary/10 blur-2xl"
      />
      <div className="rotate-1 rounded-2xl bg-primary p-7 text-primary-foreground shadow-2xl shadow-primary/30 ring-1 ring-black/10 transition-transform duration-500 hover:rotate-0">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-primary-foreground/70">
            Uygunluk Skoru
          </span>
          <span aria-label="5/5" className="text-sm tracking-wide text-gold">
            ★★★★★
          </span>
        </div>

        <div className="mt-5 flex items-end gap-2">
          <span className="font-display text-7xl font-semibold leading-none">87</span>
          <span className="mb-2 font-display text-2xl text-primary-foreground/55">/100</span>
        </div>
        <p className="mt-2 text-sm text-primary-foreground/80">
          {role} · <span className="font-medium text-gold">{match}</span>
        </p>

        {/* progress bar */}
        <div className="mt-5 h-1.5 w-full overflow-hidden rounded-full bg-primary-foreground/15">
          <div className="h-full w-[87%] rounded-full bg-gold" />
        </div>

        <dl className="mt-6 space-y-3 border-t border-primary-foreground/15 pt-5 text-sm">
          <div className="flex items-start gap-2.5">
            <span aria-hidden className="mt-1.5 size-2 shrink-0 rounded-full bg-success" />
            <dd className="text-primary-foreground/85">{strength}</dd>
          </div>
          <div className="flex items-start gap-2.5">
            <span aria-hidden className="mt-1.5 size-2 shrink-0 rounded-full bg-gold" />
            <dd className="text-primary-foreground/85">{gap}</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}
