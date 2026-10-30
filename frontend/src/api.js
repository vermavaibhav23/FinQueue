const KEY = 'finqueue.session'

export function getSession() {
  try { return JSON.parse(sessionStorage.getItem(KEY)) } catch { return null }
}
export function saveSession(tokens) { sessionStorage.setItem(KEY, JSON.stringify(tokens)) }
export function clearSession() { sessionStorage.removeItem(KEY) }

export async function api(path, options = {}, retry = true) {
  const { method = 'GET', body, headers = {} } = options
  const session = getSession()
  const response = await fetch('/api' + path, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(session?.access ? { Authorization: 'Bearer ' + session.access } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  if (response.status === 401 && retry && session?.refresh && path !== '/auth/refresh/') {
    try {
      const refreshed = await api('/auth/refresh/', {
        method: 'POST', body: { refresh: session.refresh },
      }, false)
      saveSession({ ...session, access: refreshed.access })
      return api(path, options, false)
    } catch { clearSession() }
  }
  if (response.status === 204 || response.status === 205) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail || Object.values(data || {})[0]
    const message = Array.isArray(detail) ? detail.join(' ') : detail
    const error = new Error(typeof message === 'string' ? message : 'Request failed (' + response.status + ')')
    error.status = response.status
    throw error
  }
  return data
}

