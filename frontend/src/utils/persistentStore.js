export async function getBridgeApi() {
  if (globalThis.window?.pywebview?.api) {
    return globalThis.window.pywebview.api
  }
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), 2000)
    globalThis.window?.addEventListener('pywebviewready', () => {
      clearTimeout(timer)
      resolve(globalThis.window?.pywebview?.api || null)
    }, { once: true })
  })
}

export function readLocalList(storageKey) {
  try {
    const value = globalThis.localStorage?.getItem(storageKey)
    const parsed = JSON.parse(value || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch (err) {
    console.error(`读取本地清单失败: ${storageKey}`, err)
    return []
  }
}

function writeLocalList(storageKey, list) {
  try {
    globalThis.localStorage?.setItem(storageKey, JSON.stringify(list))
  } catch (err) {
    console.error(`写入本地清单失败: ${storageKey}`, err)
  }
}

export async function hydratePersistentList(storageKey) {
  const localList = readLocalList(storageKey)
  const api = await getBridgeApi()

  if (!api?.load_store) {
    return localList
  }

  try {
    const result = await api.load_store(storageKey)
    if (Array.isArray(result?.value)) {
      const desktopList = result.value
      writeLocalList(storageKey, desktopList)
      return desktopList
    }
    if (localList.length > 0 && api.save_store) {
      await api.save_store(storageKey, localList)
    }
    return localList
  } catch (err) {
    console.error(`读取桌面清单失败: ${storageKey}`, err)
    return localList
  }
}

export async function savePersistentList(storageKey, list) {
  writeLocalList(storageKey, list)
  const api = await getBridgeApi()
  if (!api?.save_store) {
    return
  }

  try {
    await api.save_store(storageKey, list)
  } catch (err) {
    console.error(`保存桌面清单失败: ${storageKey}`, err)
  }
}
