export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body === 'object' && body !== null && 'detail' in body ? String(body.detail) : null
    throw new Error(detail ?? `リクエストに失敗しました（${res.status}）`)
  }
  return res.json() as Promise<T>
}
