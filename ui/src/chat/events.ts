import type { components } from '@/api/schema'

export type CaseEvent = components['schemas']['CopilotSessionEvent']
type EventType = CaseEvent['event_type']

/** The State tab's groups, in the order it shows them; titled by type (`chat.state.groups`). */
export const EVENT_GROUPS: readonly EventType[] = [
  'hypothesis',
  'hypothesis_discarded',
  'validated_cause',
  'evidence',
]

/** The annotations of each type, each group in the API's order (oldest first). */
export function groupEvents(events: readonly CaseEvent[]): Record<EventType, CaseEvent[]> {
  const groups: Record<EventType, CaseEvent[]> = {
    hypothesis: [],
    hypothesis_discarded: [],
    validated_cause: [],
    evidence: [],
  }
  for (const event of events) groups[event.event_type].push(event)
  return groups
}
