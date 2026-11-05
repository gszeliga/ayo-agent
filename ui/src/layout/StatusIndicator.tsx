import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ServiceDetails, StatusDot } from '@/settings/ServiceDetails'
import { useServiceHealth } from '@/settings/healthQuery'

/** Two dots in the header (database, embeddings); the details in a popover. */
export function StatusIndicator() {
  const health = useServiceHealth()
  const database = health.data?.database.status ?? 'unknown'
  const embeddings = health.data?.embeddings.status ?? 'unknown'
  const words = (state: string) => (state === 'unknown' ? 'status unknown' : state)
  return (
    <Popover>
      <PopoverTrigger
        aria-label={`Service status: database ${words(database)}, embeddings ${words(embeddings)}`}
        className="hover:bg-accent flex min-h-8 items-center gap-3 rounded-md px-2.5 text-[13px]"
      >
        <span className="flex items-center gap-1.5">
          <StatusDot state={database} />
          <span className="hidden md:inline">Database</span>
        </span>
        <span className="flex items-center gap-1.5">
          <StatusDot state={embeddings} />
          <span className="hidden md:inline">Embeddings</span>
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <ServiceDetails />
      </PopoverContent>
    </Popover>
  )
}
