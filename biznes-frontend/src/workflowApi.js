export async function workflowApi(path, { method = 'GET', body, signal } = {}) {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`/agent${path}`, {
    method, signal,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body && { 'Content-Type': 'application/json' }),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Ошибка ${response.status}`)
  return data
}
