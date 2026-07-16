'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { LayoutDashboard, Target, FileOutput, Send } from 'lucide-react'
import { cn } from '@/lib/utils'

const ITEMS = [
  { href: '/dashboard', key: 'dashboard', icon: LayoutDashboard, also: ['/cv'] },
  { href: '/score', key: 'score', icon: Target, also: [] },
  { href: '/ats', key: 'ats', icon: FileOutput, also: [] },
] as const

export function AppSidebar() {
  const t = useTranslations('sidebar')
  const pathname = usePathname()

  const isActive = (item: (typeof ITEMS)[number]) =>
    [item.href, ...item.also].some((p) => pathname === p || pathname.startsWith(p + '/'))

  return (
    <nav
      aria-label={t('label')}
      className="flex shrink-0 gap-1 overflow-x-auto border-b border-border/70 px-5 py-2 sm:px-8 md:sticky md:top-20 md:w-52 md:flex-col md:self-start md:overflow-visible md:border-b-0 md:px-0 md:py-0"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon
        const active = isActive(item)
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              active
                ? 'bg-primary/8 text-primary'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}
          >
            <Icon aria-hidden className="size-4" />
            {t(item.key)}
          </Link>
        )
      })}
      <span
        aria-disabled
        className="flex shrink-0 cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground/50"
      >
        <Send aria-hidden className="size-4" />
        {t('optimize')}
        <span className="rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider">
          {t('soon')}
        </span>
      </span>
    </nav>
  )
}
