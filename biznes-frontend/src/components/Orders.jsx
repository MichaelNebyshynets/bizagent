import { useEffect, useRef, useState } from 'react'
import { PageHead } from './ui'

const emptyFilters = { date_from: '', date_to: '', number: '' }
const statusLabel = { completed: 'Завершён', cancelled: 'Отменён' }
const money = (value) => {
  const [whole, cents = ''] = String(value).split('.')
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')},${cents.padEnd(2, '0')}`
}
const dateLabel = (date) => date.split('-').reverse().join('.')

async function load(path, signal) {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`http://localhost:8000/agent/orders${path}`, {
    signal, headers: { Authorization: `Bearer ${token}` },
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка ${response.status}`)
  return data
}

export default function Orders({ company, importSelection, clearImport }) {
  const [draft, setDraft] = useState(emptyFilters)
  const [request, setRequest] = useState({ filters: emptyFilters, before: null })
  const [list, setList] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [details, setDetails] = useState(null)
  const [detailsError, setDetailsError] = useState('')
  const detailsHeading = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(request.filters)) {
      if (value) query.set(key, value)
    }
    if (importSelection) query.set('import_id', importSelection.id)
    if (request.before) query.set('before', request.before)
    setLoading(true)
    setError('')
    load(`?${query}`, controller.signal).then((result) => {
      if (!controller.signal.aborted) {
        setList((current) => ({
          ...result,
          items: request.before ? [...current.items, ...result.items] : result.items,
        }))
      }
    }).catch((cause) => {
      if (!controller.signal.aborted) setError(cause.message)
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [request, importSelection])

  useEffect(() => {
    if (!selected) return
    detailsHeading.current?.focus()
    const controller = new AbortController()
    load(`/${selected}`, controller.signal).then((result) => {
      if (!controller.signal.aborted) setDetails(result)
    }).catch((cause) => {
      if (!controller.signal.aborted) setDetailsError(cause.message)
    })
    return () => controller.abort()
  }, [selected])

  function apply(filters) {
    setList(null)
    setSelected(null)
    setRequest({ filters, before: null })
  }

  function openOrder(id) {
    if (id === selected) return
    setDetails(null)
    setDetailsError('')
    setSelected(id)
  }

  return (
    <section>
      <PageHead company={company} tab="orders" title="Заказы" sub="Продажи вашей компании" />
      <div className="stack">
        <section className="panel">
          <form className="panel-body stack" onSubmit={(event) => {
            event.preventDefault()
            apply({ ...draft, number: draft.number.trim() })
          }}>
            {importSelection && (
              <div>Из файла <b>{importSelection.filename}</b>{' '}
                <button type="button" className="btn sm secondary" onClick={() => {
                  clearImport()
                  setDraft(emptyFilters)
                  apply(emptyFilters)
                }}>Все заказы</button>
              </div>
            )}
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
              <label>С даты<input className="input" type="date" value={draft.date_from}
                onChange={(event) => setDraft({ ...draft, date_from: event.target.value })} /></label>
              <label>По дату<input className="input" type="date" min={draft.date_from || undefined} value={draft.date_to}
                onChange={(event) => setDraft({ ...draft, date_to: event.target.value })} /></label>
              <label>Номер заказа<input className="input" value={draft.number} maxLength={100}
                onChange={(event) => setDraft({ ...draft, number: event.target.value })} /></label>
              <button className="btn" type="submit">Найти</button>
              <button className="btn secondary" type="button" onClick={() => {
                setDraft(emptyFilters)
                apply(emptyFilters)
              }}>Сбросить фильтры</button>
            </div>
          </form>
          {loading && <p className="panel-body" role="status">Загрузка заказов…</p>}
          {error && <p className="panel-body" role="alert">{error}</p>}
          {!loading && !error && !list?.items.length && <p className="panel-body">Заказы не найдены.</p>}
          {!!list?.items.length && (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead><tr><th>Номер</th><th>Дата</th><th>Клиент</th><th>Статус</th><th className="r">Сумма, BYN</th></tr></thead>
                <tbody>{list.items.map((order) => (
                  <tr key={order.id}>
                    <td><button type="button" className="btn sm secondary" aria-pressed={selected === order.id}
                      onClick={() => openOrder(order.id)}>{order.external_sale_id || `№${order.id}`}</button></td>
                    <td>{dateLabel(order.created_at)}</td><td>{order.client || '—'}</td>
                    <td>{statusLabel[order.status] || order.status}</td><td className="r num">{money(order.total)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          {!!list?.next_before && !loading && (
            <div className="panel-body"><button type="button" className="btn secondary"
              onClick={() => setRequest({ ...request, before: list.next_before })}>{error ? 'Повторить' : 'Показать ещё'}</button></div>
          )}
        </section>
        {selected && (
          <section className="panel" aria-label="Карточка заказа">
            <div className="panel-head">
              <h2 ref={detailsHeading} tabIndex={-1}>Заказ {details?.external_sale_id || `№${selected}`}</h2>
              <button type="button" className="btn sm ghost" onClick={() => openOrder(null)}>Закрыть</button>
            </div>
            {detailsError && <p className="panel-body" role="alert">{detailsError}</p>}
            {!details && !detailsError && <p className="panel-body" role="status">Загрузка позиций…</p>}
            {details && <>
              <p className="panel-body">{dateLabel(details.created_at)} · {statusLabel[details.status] || details.status}
                {details.client && ` · ${details.client}`} · <b>{money(details.total)} BYN</b></p>
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead><tr><th>Артикул</th><th>Товар</th><th className="r">Кол-во</th><th className="r">Цена, BYN</th><th className="r">Сумма, BYN</th></tr></thead>
                  <tbody>{details.lines.map((line) => (
                    <tr key={line.id}><td>{line.sku}</td><td>{line.name}</td><td className="r">{line.qty}</td>
                      <td className="r num">{money(line.price)}</td><td className="r num">{money(line.total)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </>}
          </section>
        )}
      </div>
    </section>
  )
}
