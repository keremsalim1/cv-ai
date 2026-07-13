'use client'
import { useLocale } from 'next-intl'
import { useRouter } from 'next/navigation'

export function LocaleSwitcher() {
  const locale = useLocale()
  const router = useRouter()
  const next = locale === 'tr' ? 'en' : 'tr'

  function toggle() {
    document.cookie = `locale=${next};path=/;max-age=31536000`
    router.refresh()
  }

  return (
    <button onClick={toggle} aria-label="switch language" className="text-sm font-medium">
      {next.toUpperCase()}
    </button>
  )
}
