import { newSessionId } from './sessionId'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

test('a session id is a UUID v4, new each time', () => {
  const first = newSessionId()
  expect(first).toMatch(UUID_V4)
  expect(newSessionId()).not.toBe(first)
})

test('outside a secure context it still makes one', () => {
  const original = crypto.randomUUID.bind(crypto)
  Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true })
  try {
    expect(newSessionId()).toMatch(UUID_V4)
  } finally {
    Object.defineProperty(crypto, 'randomUUID', { value: original, configurable: true })
  }
})
