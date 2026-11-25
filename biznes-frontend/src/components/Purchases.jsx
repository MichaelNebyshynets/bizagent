import { useEffect, useState } from 'react'
import { workflowApi } from '../workflowApi'
import { PageHead } from './ui'

export default function Purchases({ company, onAsk, suggestedLines }) {
  const [data, setData] = useState(null)
  const [supplier, setSupplier] = useState('')
  const [needed, setNeeded] = useState(() => Object.fromEntries(suggestedLines.map((line) => [line.product_id, line.quantity])))
  const [product, setProduct] = useState('')
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(null)
  const [requestId, setRequestId] = useState(() => crypto.randomUUID())
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    workflowApi('/purchases', { signal: controller.signal }).then(setData).catch((cause) => {
      if (!controller.signal.aborted) setError(cause.message)
    })
    return () => controller.abort()
  }, [revision])

  async function save() {
    setBusy(true)
    setError('')
    try {
      const result = await workflowApi(`/purchases?request_id=${requestId}`, {
        method: 'POST',
        body: { supplier, lines: Object.entries(needed).map(([id, quantity]) => ({ product_id: Number(id), quantity: Number(quantity) })) },
      })
      setSaved(result.id)
      setSupplier('')
      setNeeded({})
      setReview(false)
      setRequestId(crypto.randomUUID())
      setRevision((value) => value + 1)
    } catch (cause) {
      setError(cause.message)
    } finally {
      setBusy(false)
    }
  }

  const lines = data?.products.filter(({ id }) => Object.hasOwn(needed, id)) ?? []
  const valid = supplier.trim() && lines.length > 0 && lines.length <= 100 && lines.length === Object.keys(needed).length
    && lines.every(({ id }) => Number.isInteger(Number(needed[id])) && Number(needed[id]) >= 1 && Number(needed[id]) <= 1000000)

  return <section>
    <PageHead company={company} tab="purchases" title="Закупки" />
    <div className="stack">
      {error && <p role="alert">{error}</p>}
      {data && lines.length !== Object.keys(needed).length && <p role="alert">Часть товаров больше недоступна. Сбросьте черновик кнопкой «Заполнить по остаткам».</p>}
      {saved && <p role="status">Закупка №{saved} сохранена.</p>}
      {!data && !error && <p role="status">Загрузка…</p>}
      {data && <>
        <section className="panel">
          <div className="panel-head"><h2>{review ? 'Подтверждение закупки' : 'Черновик закупки'}</h2></div>
          <div className="panel-body stack">
            <fieldset disabled={review || busy} style={{ border: 0, padding: 0, margin: 0 }} className="stack">
              <label>Поставщик<input className="input" value={supplier} maxLength={255} onChange={(e) => setSupplier(e.target.value)} /></label>
              <div className="actions">
                <button type="button" className="btn secondary" onClick={() => setNeeded(
                  Object.fromEntries(data.products.filter((item) => item.stock <= 5).slice(0, 100).map((item) => [item.id, 10 - item.stock]))
                )}>Заполнить по остаткам</button>
                <button type="button" className="btn secondary" onClick={() => onAsk('Какие товары заканчиваются? Предложи количество для закупки и объясни приоритеты.')}>Спросить ассистента</button>
              </div>
              <p className="small muted">Для товаров с остатком до 5 включительно черновик предлагает пополнение до 10 единиц.</p>
              <div className="actions">
                <select className="input" value={product} aria-label="Товар" onChange={(e) => setProduct(e.target.value)}>
                  <option value="">Выберите товар</option>
                  {data.products.filter(({ id }) => !Object.hasOwn(needed, id)).map((item) =>
                    <option key={item.id} value={item.id}>{item.name} · {item.sku}</option>)}
                </select>
                <button type="button" className="btn secondary" disabled={!product || lines.length >= 100} onClick={() => {
                  setNeeded({ ...needed, [product]: 1 })
                  setProduct('')
                }}>Добавить</button>
              </div>
            </fieldset>
            {review && <p>Поставщик: <b>{supplier}</b>. Позиции: {lines.length}.</p>}
            {!!lines.length && <div style={{ overflowX: 'auto' }}><table>
              <thead><tr><th>Товар</th><th>Остаток</th><th>Количество</th>{!review && <th>Действие</th>}</tr></thead>
              <tbody>{lines.map((item) => <tr key={item.id}>
                <td>{item.name} · {item.sku}</td><td>{item.stock}</td>
                <td>{review ? needed[item.id] : <input className="input" type="number" min="1" max="1000000"
                  aria-label={`Количество: ${item.name}`} value={needed[item.id]}
                  onChange={(e) => setNeeded({ ...needed, [item.id]: e.target.value })} />}</td>
                {!review && <td><button type="button" className="btn sm secondary" onClick={() => {
                  const next = { ...needed }
                  delete next[item.id]
                  setNeeded(next)
                }}>Убрать</button></td>}
              </tr>)}</tbody>
            </table></div>}
            <div className="actions">
              {review ? <>
                <button type="button" className="btn secondary" disabled={busy} onClick={() => {
                  setReview(false)
                  setRequestId(crypto.randomUUID())
                }}>Вернуться к правкам</button>
                <button type="button" className="btn" disabled={busy} onClick={save}>Подтвердить и сохранить</button>
              </> : <button type="button" className="btn" disabled={!valid} onClick={() => {
                setError('')
                setSaved(null)
                setReview(true)
              }}>Проверить закупку</button>}
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head"><h2>Сохранённые закупки</h2></div>
          <div className="panel-body stack">
            {!data.orders.length && <p>Закупок пока нет.</p>}
            {data.orders.map((order) => <details key={order.id}>
              <summary>№{order.id} · {order.supplier} · {new Date(order.created_at).toLocaleDateString('ru-RU')}</summary>
              <ul>{order.lines.map((line) => <li key={line.sku}>{line.name} · {line.sku} · {line.quantity} шт.</li>)}</ul>
            </details>)}
          </div>
        </section>
      </>}
    </div>
  </section>
}
