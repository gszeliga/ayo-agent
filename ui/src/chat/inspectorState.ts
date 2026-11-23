import { useMediaQuery } from '@/hooks/useMediaQuery'

export type InspectorTab = 'state' | 'actions'

/** From this width the inspector is a column beside the chat; below it, a drawer. */
export const WIDE_QUERY = '(min-width: 1024px)'

export function useWideScreen(): boolean {
  return useMediaQuery(WIDE_QUERY)
}
