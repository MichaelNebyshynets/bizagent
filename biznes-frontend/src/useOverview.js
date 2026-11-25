import { useEffect, useState } from 'react'

const API = 'http://localhost:8000'

// Сводка для дашборда и аналитики (GET /agent/overview). При ошибке возвращает data=null, страницы показывают демо-данные.
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
