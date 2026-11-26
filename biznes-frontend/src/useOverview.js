import { useEffect, useState } from 'react'

const API = ''

// Сводка для дашборда и аналитики.
export function useOverview() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    const token = localStorage.getItem('auth_token')
    fetch(`${API}/agent/overview`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Ошибка ${r.status}`))))
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [])
  return { data, error }
}
