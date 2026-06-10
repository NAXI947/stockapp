import assert from 'node:assert/strict'

const localStorageData = new Map()

globalThis.localStorage = {
  getItem(key) {
    return localStorageData.has(key) ? localStorageData.get(key) : null
  },
  setItem(key, value) {
    localStorageData.set(key, String(value))
  },
  removeItem(key) {
    localStorageData.delete(key)
  },
  clear() {
    localStorageData.clear()
  },
}

const desktopData = new Map()

globalThis.window = {
  pywebview: {
    api: {
      async load_store(key) {
        return desktopData.has(key)
          ? { ok: true, value: desktopData.get(key) }
          : { ok: true, value: null }
      },
      async save_store(key, value) {
        desktopData.set(key, value)
        return { ok: true }
      },
    },
  },
}

const {
  hydratePersistentList,
  readLocalList,
  savePersistentList,
} = await import('../src/utils/persistentStore.js')

localStorage.clear()
desktopData.clear()

localStorage.setItem('stocknew_watchlist', JSON.stringify([{ tsCode: '000001.SZ', name: 'local' }]))
assert.deepEqual(readLocalList('stocknew_watchlist'), [{ tsCode: '000001.SZ', name: 'local' }])

await savePersistentList('stocknew_watchlist', [{ tsCode: '000002.SZ', name: 'saved' }])
assert.deepEqual(JSON.parse(localStorage.getItem('stocknew_watchlist')), [{ tsCode: '000002.SZ', name: 'saved' }])
assert.deepEqual(desktopData.get('stocknew_watchlist'), [{ tsCode: '000002.SZ', name: 'saved' }])

localStorage.clear()
desktopData.set('stocknew_watchlist', [{ tsCode: '000003.SZ', name: 'desktop' }])
const hydrated = await hydratePersistentList('stocknew_watchlist')
assert.deepEqual(hydrated, [{ tsCode: '000003.SZ', name: 'desktop' }])
assert.deepEqual(JSON.parse(localStorage.getItem('stocknew_watchlist')), [{ tsCode: '000003.SZ', name: 'desktop' }])

localStorage.clear()
desktopData.clear()
localStorage.setItem('stocknew_watchlist', JSON.stringify([{ tsCode: '000004.SZ', name: 'migrated' }]))
const migrated = await hydratePersistentList('stocknew_watchlist')
assert.deepEqual(migrated, [{ tsCode: '000004.SZ', name: 'migrated' }])
assert.deepEqual(desktopData.get('stocknew_watchlist'), [{ tsCode: '000004.SZ', name: 'migrated' }])

localStorage.clear()
desktopData.clear()
localStorage.setItem('stocknew_watchlist', JSON.stringify([{ tsCode: '000005.SZ', name: 'stale' }]))
desktopData.set('stocknew_watchlist', [])
const emptyDesktopList = await hydratePersistentList('stocknew_watchlist')
assert.deepEqual(emptyDesktopList, [])
assert.deepEqual(JSON.parse(localStorage.getItem('stocknew_watchlist')), [])
