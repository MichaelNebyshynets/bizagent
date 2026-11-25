import { useEffect, useState } from 'react'

export default function SalesImportHistory({ load, onClose, onImportOrders }) {
  const [pages, setPages] = useState([])
  const [before, setBefore] = useState(null)
  const [next, setNext] = useState(null)
  const [retry, setRetry] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    load(before, controller.signal).then((page) => {
      if (controller.signal.aborted) return
      setPages((items) => before ? [...items, ...page.items] : page.items)
      setNext(page.next_before)
    }).catch((cause) => {
      if (!controller.signal.aborted) setError(cause.message)
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [load, before, retry])

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>История импорта продаж</h2>
        <button type="button" className="btn sm ghost" onClick={onClose}>Закрыть</button>
      </div>
      <div className="panel-body stack">
        {loading && <p role="status">Загрузка истории…</p>}
        {error && <>
          <p role="alert">Не удалось загрузить историю. {error}</p>
          <div><button type="button" className="btn sm secondary" onClick={() => setRetry((value) => value + 1)}>Повторить</button></div>
        </>}
        {!loading && !error && !pages.length && <p>Сохранённых импортов пока нет.</p>}
        {!!pages.length && (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead><tr><th>Файл</th><th>Когда</th><th>Кто загрузил</th><th>Заказов</th><th>Строк</th><th>Повторов</th><th>Выручка, BYN</th></tr></thead>
              <tbody>
                {pages.map((item) => (
                  <tr key={item.id}>
                    <td>{item.filename}</td>
                    <td>{new Date(item.created_at).toLocaleString('ru-RU')}</td>
                    <td>{item.author || `ID ${item.user_id}`}</td>
                    <td>{item.has_orders && onImportOrders
                      ? <button type="button" className="btn sm secondary" onClick={() => onImportOrders(item)}>Открыть ({item.orders})</button>
                      : item.orders}</td>
                    <td>{item.rows}</td>
                    <td>{item.duplicates}</td>
                    <td>{item.revenue.replace('.', ',')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && next && (
          <div><button type="button" className="btn sm secondary" onClick={() => setBefore(next)}>Показать ещё</button></div>
        )}
      </div>
    </section>
  )
}
