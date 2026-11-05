import { clearConnection, loadConnection, saveConnection } from './storage'

const CONNECTION = { baseUrl: 'http://api.test', apiKey: 'k' }

test('saves, loads and clears the connection in sessionStorage', () => {
  saveConnection(CONNECTION)
  expect(loadConnection()).toEqual(CONNECTION)
  expect(window.localStorage.length).toBe(0)

  clearConnection()
  expect(loadConnection()).toBeNull()
})

test.each(['not json', '{"baseUrl": 1}', 'null', '[]'])('ignores a stored %j', (raw) => {
  window.sessionStorage.setItem('ayo.connection', raw)

  expect(loadConnection()).toBeNull()
})

test('blocked storage never throws', () => {
  const blocked = {
    getItem: () => {
      throw new DOMException('blocked', 'SecurityError')
    },
    setItem: () => {
      throw new DOMException('blocked', 'SecurityError')
    },
    removeItem: () => {
      throw new DOMException('blocked', 'SecurityError')
    },
  } as unknown as Storage

  expect(() => {
    saveConnection(CONNECTION, blocked)
    clearConnection(blocked)
  }).not.toThrow()
  expect(loadConnection(blocked)).toBeNull()
})
