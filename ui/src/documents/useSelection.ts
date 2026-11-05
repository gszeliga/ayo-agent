import { useState } from 'react'

import type { components } from '@/api/schema'

type Document = components['schemas']['Document']

/** What the confirmation needs about a selected document, wherever its page is. */
export interface Selected {
  title: string
  chunks: number
}

export interface Selection {
  items: Map<string, Selected>
  has: (docId: string) => boolean
  toggle: (doc: Document) => void
  /** Selects (or unselects) every document on the page. */
  setAll: (docs: Document[], selected: boolean) => void
  remove: (docIds: string[]) => void
  clear: () => void
}

/**
 * Selected documents, kept across pages and sorts. A new `scope` (tenant or search)
 * clears it: the selected rows may not be in view any more. In memory only, never in the URL.
 */
export function useSelection(scope: string): Selection {
  const [items, setItems] = useState(() => new Map<string, Selected>())
  const [currentScope, setCurrentScope] = useState(scope)
  if (scope !== currentScope) {
    setCurrentScope(scope)
    if (items.size > 0) setItems(new Map())
  }

  const describe = (doc: Document): Selected => ({
    title: doc.title ?? doc.source_key,
    chunks: doc.chunk_count,
  })

  return {
    items,
    has: (docId) => items.has(docId),
    toggle: (doc) => {
      setItems((current) => {
        const next = new Map(current)
        if (next.has(doc.doc_id)) next.delete(doc.doc_id)
        else next.set(doc.doc_id, describe(doc))
        return next
      })
    },
    setAll: (docs, selected) => {
      setItems((current) => {
        const next = new Map(current)
        for (const doc of docs) {
          if (selected) next.set(doc.doc_id, describe(doc))
          else next.delete(doc.doc_id)
        }
        return next
      })
    },
    remove: (docIds) => {
      setItems((current) => {
        const next = new Map(current)
        for (const docId of docIds) next.delete(docId)
        return next
      })
    },
    clear: () => {
      setItems(new Map())
    },
  }
}
