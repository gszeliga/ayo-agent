import type { components } from '@/api/schema'

import { caseStatus, structuredSummary } from './structuredSummary'

type CaseDetail = components['schemas']['CaseDetail']

/** The case summed up from its record: no model call, always current. Plain text. */
export function StructuredSummary({ detail }: { detail: CaseDetail }) {
  return (
    <section aria-labelledby="structured-summary" className="space-y-3">
      <div>
        <h2 id="structured-summary" className="text-sm font-semibold">
          Structured summary
        </h2>
        <p className="text-muted-foreground text-xs">
          From the case record, no model call. {caseStatus(detail)}.
        </p>
      </div>
      {structuredSummary(detail).map((section) => (
        <div key={section.title} role="group" aria-label={section.title} className="space-y-1">
          <h3 className="text-xs font-semibold">{section.title}</h3>
          {section.items.length === 0 ? (
            <p className="text-muted-foreground text-sm italic">{section.empty}</p>
          ) : (
            <ul className="list-disc space-y-0.5 pl-5 text-sm">
              {section.items.map((item, i) => (
                <li key={i} className="break-words whitespace-pre-wrap">
                  {item}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  )
}
