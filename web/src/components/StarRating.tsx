export function StarRating({ stars }: { stars: number }) {
  const n = Math.min(5, Math.max(1, Math.round(stars)))
  return (
    <span aria-label={`${n}/5`} className="text-2xl leading-none tracking-[0.12em]">
      <span className="text-gold">{'★'.repeat(n)}</span>
      <span className="text-muted-foreground/35">{'☆'.repeat(5 - n)}</span>
    </span>
  )
}
