'use client'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

export default function Home() {
  const t = useTranslations('landing')
  return (
    <main className="mx-auto flex max-w-2xl flex-col items-center gap-6 px-4 py-24 text-center">
      <h1 className="text-4xl font-bold">{t('title')}</h1>
      <p className="text-lg text-muted-foreground">{t('subtitle')}</p>
      {/* Base UI Button: use render (asChild is Radix-only) */}
      <Button size="lg" render={<Link href="/register" />}>
        {t('cta')}
      </Button>
    </main>
  )
}
