'use client'
import { usePathname } from 'next/navigation'
import { motion } from 'motion/react'
import { AppSidebar } from '@/components/AppSidebar'
import { flow } from '@/lib/motion'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col md:flex-row md:gap-6 md:px-8 md:pt-10">
      <AppSidebar />
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={flow}
        className="min-w-0 flex-1"
      >
        {children}
      </motion.div>
    </div>
  )
}
