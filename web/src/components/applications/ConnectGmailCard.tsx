'use client'
import { Mail } from 'lucide-react'
import { motion } from 'motion/react'
import { useTranslations } from 'next-intl'
import { snap } from '@/lib/motion'
import {
  GMAIL_REDIRECT_PATH, gmailConsentUrl, newOAuthState, rememberOAuthState,
} from '@/lib/gmailOAuth'

export function ConnectGmailCard() {
  const t = useTranslations('applications')

  function connect() {
    // Generated on click, not during render: a value produced on the server
    // and again on the client would differ and break hydration.
    const state = newOAuthState()
    rememberOAuthState(state)
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? ''
    const redirect = window.location.origin + GMAIL_REDIRECT_PATH
    window.location.href = gmailConsentUrl(clientId, redirect, state)
  }

  return (
    <section className="grain flex flex-col items-start gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-10">
      <span className="grid size-11 place-items-center rounded-full bg-primary/8 text-primary ring-1 ring-primary/12">
        <Mail aria-hidden className="size-5" />
      </span>
      <p className="type-body max-w-[65ch] text-muted-foreground">
        {t('connectExplain')}
      </p>
      <motion.button
        type="button"
        onClick={connect}
        whileHover={{ y: -2 }}
        whileTap={{ scale: 0.98, transition: snap }}
        className="type-ui inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-primary-foreground shadow-md shadow-primary/20 hover:bg-primary/90"
      >
        {t('connect')}
      </motion.button>
    </section>
  )
}
