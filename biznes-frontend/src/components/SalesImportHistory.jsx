import { useEffect, useState } from 'react'
import { workflowApi } from '../workflowApi'

export default function SalesImportHistory({ load, onClose, onImportOrders }) {
  const [pages, setPages] = useState([])
  const [before, setBefore] = useState(null)
  const [next, setNext] = useState(null)
  const [retry, setRetry] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reversal, setReversal] = useState(null)
  const [reversing, setReversing] = useState(false)
  const [reversalError, setReversalError] = useState('')
  const [notice, setNotice] = useState('')

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

  async function reverse(id, confirm) {
    setReversing(true)
    setReversalError('')
    setNotice('')
    try {
      const result = await workflowApi(`/sales/imports/${id}/reverse?confirm=${confirm}`, { method: 'POST' })
      if (result.reversed_at) {
        setReversal(null)
        setPages((previous) => previous.map((item) => item.id === id ? { ...item, ...result } : item))
        setNotice(`Импорт «${result.filename}» отменён.`)
      } else {
        setReversal(result)
      }
    } catch (cause) {
      setReversalError(cause.message)
    } finally {
      setReversing(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>История импорта продаж</h2>
        <button type="button" className="btn sm ghost" onClick={onClose}>Закрыть</button>
      </div>
      <div className="panel-body stack">
        {reversalError && <p role="alert">{reversalError}</p>}
        {notice && <p role="status">{notice}</p>}
        {reversal && <section className="stack" aria-label="Подтверждение отмены импорта">
          <h3>Отменить импорт «{reversal.filename}»?</h3>
          <p>Заказы останутся в реестре со статусом «Отменён». Графики и сводки уменьшатся на указанные суммы.</p>
          <ul>{reversal.periods.map((period) => <li key={period.month}>
            {period.month.slice(0, 7)} · заказов: −{period.orders} · выручка: −{period.revenue.replace('.', ',')} BYN
          </li>)}</ul>
          <div className="actions">
            <button type="button" className="btn secondary" disabled={reversing} onClick={() => setReversal(null)}>Назад</button>
            <button type="button" className="btn" disabled={reversing} onClick={() => reverse(reversal.id, true)}>Подтвердить отмену</button>
          </div>
        </section>}
        {loading && <p role="status">Загрузка истории…</p>}
        {error && <>
          <p role="alert">Не удалось загрузить историю. {error}</p>
          <div><button type="button" className="btn sm secondary" onClick={() => setRetry((value) => value + 1)}>Повторить</button></div>
        </>}
        {!loading && !error && !pages.length && <p>Сохранённых импортов пока нет.</p>}
        {!!pages.length && (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead><tr><th>Файл</th><th>Когда</th><th>Кто загрузил</th><th>Заказов</th><th>Строк</th><th>Повторов</th><th>Выручка, BYN</th><th>Статус</th></tr></thead>
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
                    <td>{item.reversed_at
                      ? <>Отменён · {new Date(item.reversed_at).toLocaleString('ru-RU')}{item.reversed_by_name && ` · ${item.reversed_by_name}`}</>
                      : item.has_orders ? <button type="button" className="btn sm secondary"
                          disabled={reversing || !!reversal} onClick={() => reverse(item.id, false)}>Отменить импорт</button> : <span className="muted">Нет связи с заказами</span>}
                    </td>
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
