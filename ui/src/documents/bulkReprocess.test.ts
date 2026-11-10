import { ApiError } from '@/api/errors'

import { runBulkReprocess, type Progress, type ReprocessOne, type Target } from './bulkReprocess'

const targets = (n: number): Target[] =>
  Array.from({ length: n }, (_, i) => ({
    docId: `upload-${String(i + 1)}`,
    title: `Doc ${String(i + 1)}`,
  }))

const apiError = (status: number | null, type = 'x') =>
  status === null
    ? ApiError.network(new TypeError('fetch failed'))
    : new ApiError(status, [{ type, loc: [], msg: type }])

/** A reprocess that answers from a table by doc id; `indexed` by default. */
function fake(answers: Record<string, 'up_to_date' | Error> = {}) {
  const calls: string[] = []
  const reprocess: ReprocessOne = (docId) => {
    calls.push(docId)
    const answer = answers[docId]
    if (answer instanceof Error) return Promise.reject(answer)
    return Promise.resolve({ status: answer ?? 'indexed' })
  }
  return { calls, reprocess }
}

test('every document runs once, in order, and is counted by its outcome', async () => {
  const { calls, reprocess } = fake({
    'upload-2': 'up_to_date',
    'upload-3': apiError(404, 'document_not_found'),
    'upload-4': apiError(409, 'document_changed'),
  })

  const result = await runBulkReprocess(targets(5), reprocess)

  expect(calls).toEqual(['upload-1', 'upload-2', 'upload-3', 'upload-4', 'upload-5'])
  expect(result.counts).toEqual({ reprocessed: 2, up_to_date: 1, changed: 1, gone: 1, failed: 0 })
  expect([...result.outcomes]).toEqual([
    ['upload-1', 'reprocessed'],
    ['upload-2', 'up_to_date'],
    ['upload-3', 'gone'],
    ['upload-4', 'changed'],
    ['upload-5', 'reprocessed'],
  ])
  expect(result.stopped).toBeNull()
  expect(result.notStarted).toBe(0)
})

test('progress names the current document, then reports none at the end', async () => {
  const seen: Progress[] = []

  await runBulkReprocess(targets(2), fake().reprocess, { onProgress: (p) => seen.push(p) })

  expect(seen.map((p) => [p.done, p.total, p.current?.docId ?? null])).toEqual([
    [0, 2, 'upload-1'],
    [1, 2, 'upload-2'],
    [2, 2, null],
  ])
  expect(seen.at(-1)?.counts.reprocessed).toBe(2)
})

test('a stop takes effect between documents', async () => {
  let stop = false
  const { calls, reprocess } = fake()
  const stopAfterSecond: ReprocessOne = async (docId) => {
    const result = await reprocess(docId)
    if (calls.length === 2) stop = true
    return result
  }

  const result = await runBulkReprocess(targets(4), stopAfterSecond, { shouldStop: () => stop })

  expect(calls).toEqual(['upload-1', 'upload-2'])
  expect(result.stopped).toEqual({ by: 'user' })
  expect(result.notStarted).toBe(2)
})

test.each([
  ['the provider failing', apiError(502, 'embedding_failed')],
  ['the network failing', apiError(null)],
  ['the key being rejected', apiError(401, 'invalid_api_key')],
  ['anything unexpected', new Error('boom')],
])('%s stops the run at that document', async (_, error) => {
  const { calls, reprocess } = fake({ 'upload-2': error })

  const result = await runBulkReprocess(targets(4), reprocess)

  expect(calls).toEqual(['upload-1', 'upload-2'])
  expect(result.counts).toMatchObject({ reprocessed: 1, failed: 1 })
  expect(result.stopped).toEqual({ by: 'error', error, target: targets(4)[1] })
  expect(result.notStarted).toBe(2)
})

test('a thrown non-error is wrapped, never rethrown', async () => {
  const reprocess: ReprocessOne = () => Promise.reject(new Error('x'))
  const odd: ReprocessOne = (docId) =>
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
    docId === 'upload-1' ? Promise.reject('down') : reprocess(docId)

  const result = await runBulkReprocess(targets(2), odd)

  expect(result.stopped).toMatchObject({ by: 'error', error: new Error('down') })
})

test('nothing to do', async () => {
  const result = await runBulkReprocess([], fake().reprocess)

  expect(result).toMatchObject({ stopped: null, notStarted: 0 })
  expect(result.outcomes.size).toBe(0)
})
