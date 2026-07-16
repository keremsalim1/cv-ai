'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { MailCheck } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { GoogleIcon } from '@/components/GoogleIcon'

export default function RegisterPage() {
  const t = useTranslations('auth')
  const supabase = createClient()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo: `${location.origin}/auth/callback`,
      },
    })
    if (error) {
      setError(error.message)
      return
    }
    setDone(true)
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
        <h1 className="text-center font-display text-3xl font-semibold tracking-tight text-ink">
          {t('registerTitle')}
        </h1>

        <Card className="mt-7 gap-5 p-7 shadow-xl shadow-primary/5">
          {done ? (
            <div className="flex flex-col items-center gap-4 py-6 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-success/12 text-success">
                <MailCheck aria-hidden className="size-6" />
              </span>
              <p className="text-[15px] leading-relaxed text-foreground">{t('checkEmail')}</p>
            </div>
          ) : (
            <>
              <form onSubmit={onSubmit} className="flex flex-col gap-4">
                <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
                  {t('fullNameLabel')}
                  <Input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                    className="h-11 text-base"
                    placeholder="Ada Lovelace"
                  />
                </label>
                <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
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
                <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
                  {t('passwordLabel')}
                  <Input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    className="h-11 text-base"
                    placeholder="En az 8 karakter"
                  />
                </label>
                {error && (
                  <p className="rounded-md bg-destructive/8 px-3 py-2 text-sm text-destructive">{error}</p>
                )}
                <Button type="submit" className="h-11 text-base">{t('registerButton')}</Button>
              </form>

              <div className="hairline" />

              <Button variant="outline" onClick={google} className="h-11 gap-2.5 text-base">
                <GoogleIcon className="size-[18px]" />
                {t('googleButton')}
              </Button>

              <Link
                href="/login"
                className="text-center text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
              >
                {t('haveAccount')}
              </Link>
            </>
          )}
        </Card>
      </div>
    </main>
  )
}
