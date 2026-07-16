'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import type { User } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase/client'
import { LocaleSwitcher } from '@/components/LocaleSwitcher'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function NavBar() {
  const t = useTranslations('nav')
  const router = useRouter()
  const supabase = createClient()
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUser(data.user))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
    })
    return () => subscription.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function logout() {
    const { error } = await supabase.auth.signOut()
    // Server-side revocation can fail on a stale session; still drop it locally
    if (error) await supabase.auth.signOut({ scope: 'local' })
    setUser(null)
    router.push('/')
    router.refresh()
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5 sm:px-8">
        <Link href="/" className="group flex items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-6 place-items-center rounded-[5px] bg-primary font-display text-[13px] font-semibold leading-none text-primary-foreground shadow-sm transition-transform duration-200 group-hover:-rotate-6"
          >
            C
          </span>
          <span className="font-display text-[17px] font-semibold tracking-tight text-ink">
            {t('appName')}
          </span>
        </Link>

        <nav className="flex items-center gap-1 text-sm sm:gap-2">
          <LocaleSwitcher />
          <span aria-hidden className="mx-1 h-4 w-px bg-border" />
          {user ? (
            <>
              <Link
                href="/dashboard"
                className="rounded-md px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {t('dashboard')}
              </Link>
              <Button variant="outline" size="sm" onClick={logout}>
                {t('logout')}
              </Button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-md px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {t('login')}
              </Link>
              <Link href="/register" className={cn(buttonVariants({ size: 'sm' }))}>
                {t('register')}
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}
