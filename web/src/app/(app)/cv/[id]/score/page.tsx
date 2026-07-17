import { redirect } from 'next/navigation'

export default async function LegacyScoreRedirect({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  redirect(`/score?cv=${id}`)
}
