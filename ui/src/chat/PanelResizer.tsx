import { useRef } from 'react'

import { clampWidth, type PanelLimits } from './panelWidth'

const STEP = 16

interface Props {
  /** "Resize inspector", "Resize cases list". */
  label: string
  /** The column's edge the handle sits on: the side it grows towards. */
  edge: 'left' | 'right'
  width: number
  limits: PanelLimits
  onResize: (width: number) => void
}

/** The row the column sits in (the handle's grandparent): it caps the width (0 if unknown). */
function rowWidth(handle: HTMLElement): number {
  return handle.parentElement?.parentElement?.getBoundingClientRect().width ?? 0
}

/**
 * A column's edge as a handle: drag it, or focus it and use the arrows (the one pointing
 * away from the column widens it), Home (narrowest) and End (widest); a double click goes
 * back to the default width. Place it inside the column, which must be `relative`.
 */
export function PanelResizer({ label, edge, width, limits, onResize }: Props) {
  const drag = useRef<{ x: number; width: number } | null>(null)
  const outwards = edge === 'left' ? -1 : 1

  function resize(handle: HTMLElement, next: number) {
    onResize(clampWidth(next, limits, rowWidth(handle)))
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={limits.min}
      aria-valuemax={limits.max}
      aria-valuetext={`${String(width)} pixels wide`}
      tabIndex={0}
      className={
        'group focus-visible:ring-ring/50 absolute top-0 z-10 flex h-full w-4 cursor-col-resize touch-none justify-center outline-none focus-visible:ring-[3px] ' +
        (edge === 'left' ? '-left-2' : '-right-2')
      }
      onPointerDown={(event) => {
        if (event.button !== 0) return
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = { x: event.clientX, width }
      }}
      onPointerMove={(event) => {
        const start = drag.current
        if (start) {
          resize(event.currentTarget, start.width + outwards * (event.clientX - start.x))
        }
      }}
      onPointerUp={(event) => {
        drag.current = null
        event.currentTarget.releasePointerCapture(event.pointerId)
      }}
      onPointerCancel={() => {
        drag.current = null
      }}
      onDoubleClick={(event) => {
        resize(event.currentTarget, limits.default)
      }}
      onKeyDown={(event) => {
        const next = {
          ArrowLeft: width - outwards * STEP,
          ArrowRight: width + outwards * STEP,
          Home: limits.min,
          End: limits.max,
        }[event.key]
        if (next === undefined) return
        event.preventDefault()
        resize(event.currentTarget, next)
      }}
    >
      {/* The visible line: the column's border, thicker on hover, drag and focus. */}
      <span
        aria-hidden="true"
        className="bg-border group-hover:bg-primary/60 group-focus-visible:bg-primary group-active:bg-primary h-full w-px transition-all group-hover:w-0.5 group-active:w-0.5"
      />
    </div>
  )
}
