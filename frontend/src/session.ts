import { reactive } from 'vue'

export interface SessionState {
  ready: boolean
  user: string
  fullName: string
  image: string | null
  hasAccess: boolean
  isManager: boolean
  error: string | null
}

// Boot values come from www/supabill.py; the server re-checks every request.
export const session = reactive<SessionState>({
  ready: false,
  user: window.sb_user || '',
  fullName: window.sb_full_name || '',
  image: null,
  hasAccess: !!window.sb_has_access,
  isManager: !!window.sb_is_manager,
  error: null,
})

export function loginUrl(): string {
  return '/login?redirect-to=' + encodeURIComponent(window.location.pathname)
}

export async function loadSession(): Promise<void> {
  try {
    const res = await fetch('/api/method/supabill.api.session.get_session', {
      headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
      credentials: 'same-origin',
    })
    if (res.status === 401 || res.status === 403) {
      window.location.href = loginUrl()
      return
    }
    if (!res.ok) throw new Error(`Server returned ${res.status}`)
    const { message: m } = await res.json()
    Object.assign(session, {
      user: m.user,
      fullName: m.full_name,
      image: m.user_image,
      hasAccess: m.has_access,
      isManager: m.is_manager,
      error: null,
    })
  } catch (e) {
    session.error = e instanceof Error ? e.message : String(e)
  } finally {
    session.ready = true
  }
}

export async function logout(): Promise<void> {
  await fetch('/api/method/logout', {
    method: 'POST',
    headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' },
    credentials: 'same-origin',
  })
  window.location.href = '/login'
}
