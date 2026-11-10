/** Small wrapper over Frappe's method API with readable error messages. */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function serverMessage(body: any): string | null {
  try {
    if (body?._server_messages) {
      const msgs = JSON.parse(body._server_messages).map((m: string) => JSON.parse(m).message)
      return msgs.join(' ').replace(/<[^>]+>/g, '')
    }
  } catch { /* fall through */ }
  if (body?.exception) return String(body.exception).split(':').slice(1).join(':').trim() || body.exception
  return null
}

export async function call<T = any>(method: string, args: Record<string, unknown> = {}, opts: { get?: boolean } = {}): Promise<T> {
  const url = '/api/method/' + method
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' }
  let res: Response
  if (opts.get) {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(args)) if (v !== undefined && v !== null) q.set(k, typeof v === 'object' ? JSON.stringify(v) : String(v))
    res = await fetch(url + (q.toString() ? '?' + q : ''), { headers, credentials: 'same-origin' })
  } else {
    headers['Content-Type'] = 'application/json'
    res = await fetch(url, { method: 'POST', headers, credentials: 'same-origin', body: JSON.stringify(args) })
  }
  let body: any = null
  try { body = await res.json() } catch { /* non-JSON */ }
  if (!res.ok) {
    if (res.status === 401) window.location.href = '/login?redirect-to=' + encodeURIComponent(location.pathname)
    throw new ApiError(serverMessage(body) || `Request failed (${res.status})`, res.status)
  }
  return body?.message as T
}

export function newRequestId(): string {
  return (crypto as any).randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)
}

/** Uploads a file as a private Frappe File and returns its URL. */
export async function uploadFile(file: File): Promise<string> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  fd.append('is_private', '1')
  fd.append('folder', 'Home')
  const res = await fetch('/api/method/upload_file', {
    method: 'POST', body: fd, credentials: 'same-origin',
    headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
  })
  let body: any = null
  try { body = await res.json() } catch { /* non-JSON */ }
  if (!res.ok) throw new ApiError(serverMessage(body) || `Upload failed (${res.status})`, res.status)
  return body.message.file_url as string
}
