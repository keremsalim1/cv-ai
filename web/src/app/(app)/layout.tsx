import { AppSidebar } from '@/components/AppSidebar'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col md:flex-row md:gap-6 md:px-8 md:pt-10">
      <AppSidebar />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
