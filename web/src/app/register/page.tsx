'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

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
    <main className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-16">
      <Card className="flex flex-col gap-4 p-6">
        <h1 className="text-xl font-semibold">{t('registerTitle')}</h1>
        {done ? (
          <p className="text-sm">{t('checkEmail')}</p>
        ) : (
          <>
            <form onSubmit={onSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-sm">
                {t('fullNameLabel')}
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t('emailLabel')}
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t('passwordLabel')}
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
              </label>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <Button type="submit">{t('registerButton')}</Button>
            </form>
            <Button variant="outline" onClick={google}>{t('googleButton')}</Button>
            <Link href="/login" className="text-sm underline">{t('haveAccount')}</Link>
          </>
        )}
      </Card>
    </main>
  )
}
