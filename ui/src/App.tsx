/** Placeholder until the connection screen (U3): shows that the theme and fonts load. */
export function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-6">
      <div className="flex items-center gap-3">
        <div
          aria-hidden="true"
          className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md text-[13px] font-bold"
        >
          AYO
        </div>
        <h1 className="text-lg font-semibold">AYO Admin</h1>
      </div>
      <div className="bg-card shadow-elevated rounded-xl border p-5">
        <p>The admin UI is being built. Nothing here talks to the API yet.</p>
        <p className="text-muted-foreground mt-2">
          API types generated from{' '}
          <code className="font-mono text-[12.5px]">docs/openapi.json</code>.
        </p>
      </div>
    </main>
  )
}
