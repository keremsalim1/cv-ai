'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

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
    <main className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-16">
      <Card className="flex flex-col gap-4 p-6">
        <h1 className="text-xl font-semibold">{t('loginTitle')}</h1>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('emailLabel')}
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('passwordLabel')}
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit">{t('loginButton')}</Button>
        </form>
        <Button variant="outline" onClick={google}>{t('googleButton')}</Button>
        <Link href="/register" className="text-sm underline">{t('noAccount')}</Link>
      </Card>
    </main>
  )
}
