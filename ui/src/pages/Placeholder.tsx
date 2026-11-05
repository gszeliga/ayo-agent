/** Stands in for a screen that a later step builds. */
export function Placeholder({ title, step }: { title: string; step: string }) {
  return (
    <section className="space-y-2">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="text-muted-foreground">Coming in step {step}.</p>
    </section>
  )
}
