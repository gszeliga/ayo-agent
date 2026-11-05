// Generates src/api/schema.d.ts from the API's committed contract, ../docs/openapi.json.
// `--check` only compares, and fails if the committed file is stale.
import { readFile, writeFile } from 'node:fs/promises'
import { argv, exit } from 'node:process'

import openapiTS, { astToString } from 'openapi-typescript'

const spec = new URL('../../docs/openapi.json', import.meta.url)
const target = new URL('../src/api/schema.d.ts', import.meta.url)
const HEADER =
  '// Generated from docs/openapi.json by `pnpm gen:api` (openapi-typescript). Do not edit.\n\n'

const generated = HEADER + astToString(await openapiTS(spec))

if (argv.includes('--check')) {
  const current = await readFile(target, 'utf8').catch(() => '')
  if (current !== generated) {
    console.error('src/api/schema.d.ts is stale: run `pnpm gen:api` and commit it.')
    exit(1)
  }
  console.log('src/api/schema.d.ts is up to date')
} else {
  await writeFile(target, generated)
  console.log('wrote src/api/schema.d.ts')
}
