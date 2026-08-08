'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { GoogleIcon } from '@/components/GoogleIcon'

export default function LoginPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const supabase = createClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      setError(error.message)
      return
    }
    router.push('/dashboard')
    router.refresh()
  }

  async function google() {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${location.origin}/auth/callback` },
    })
  }

  return (
    <main className="oxblood-wash grain relative flex min-h-[calc(100dvh-3.5rem)] items-center justify-center px-5 py-14">
      <div className="w-full max-w-sm">
        <h1 className="type-title text-center text-ink">
          {t('loginTitle')}
        </h1>

        <Card className="mt-7 gap-5 p-7 shadow-e1 ring-foreground/[0.07]">
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <label className="type-ui flex flex-col gap-1.5 text-foreground">
              {t('emailLabel')}
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-11 text-base"
                placeholder="ada@ornek.com"
              />
            </label>
            <label className="type-ui flex flex-col gap-1.5 text-foreground">
              {t('passwordLabel')}
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-11 text-base"
                placeholder="••••••••"
              />
            </label>
            {error && (
              <p className="type-meta rounded-md bg-destructive/8 px-3 py-2 text-destructive">{error}</p>
            )}
            <Button type="submit" className="h-11 text-base">{t('loginButton')}</Button>
          </form>

          <div className="hairline" />

          <Button variant="outline" onClick={google} className="h-11 gap-2.5 text-base">
            <GoogleIcon className="size-[18px]" />
            {t('googleButton')}
          </Button>

          <Link
            href="/register"
            className="type-ui text-center text-muted-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
          >
            {t('noAccount')}
          </Link>
        </Card>
      </div>
    </main>
  )
}
