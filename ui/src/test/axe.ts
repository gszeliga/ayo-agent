import axe from 'axe-core'

/**
 * The accessibility violations axe finds under `node`. A baseline, not an audit: jsdom has
 * no layout, so rules that need rendering (colour contrast) are off.
 */
export async function a11yViolations(node: Element = document.body): Promise<string[]> {
  const results = await axe.run(node, { rules: { 'color-contrast': { enabled: false } } })
  return results.violations.map(
    (v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(', ')})`,
  )
}
