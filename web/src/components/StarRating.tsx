export function StarRating({ stars }: { stars: number }) {
  const n = Math.min(5, Math.max(1, Math.round(stars)))
  return (
    <span aria-label={`${n}/5`} className="text-xl tracking-wide">
      {'★'.repeat(n)}
      {'☆'.repeat(5 - n)}
    </span>
  )
}
