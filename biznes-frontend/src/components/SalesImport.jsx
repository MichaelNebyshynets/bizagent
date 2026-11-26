import { useState } from 'react'

const monthFormat = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' })

export default function SalesImport({ file, onClose, onImported }) {
  const [preview, setPreview] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function upload(confirm) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const body = new FormData()
      body.append('file', file)
      body.append('confirm', String(confirm))
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/agent/sales/import', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body,
      })
      const result = await response.json()
      if (!response.ok) {
        throw new Error(typeof result.detail === 'string' ? result.detail : `Ошибка ${response.status}`)
      }
      setPreview(result)
      if (confirm && !result.errors.length) {
        setPreview(null)
        setMessage(`Сохранено заказов: ${result.imported}. Пропущено строк уже загруженных заказов: ${result.duplicates}.`)
        onImported?.()
      }
    } catch (cause) {
      setError(cause.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2>Импорт продаж</h2><button type="button" className="btn sm ghost" disabled={busy} onClick={onClose}>Закрыть</button></div>
      <div className="panel-body stack">
        <p>CSV в UTF-8 с колонками <code>date,order_id,sku,quantity,price</code>. Дата в формате ГГГГ-ММ-ДД, цена в BYN через точку. Замените примерные значения своими. Артикулы должны совпадать с колонкой SKU в каталоге товаров вашей компании.</p>
        <p><b>Файл:</b> {file.name}</p>
        <div>
          <button type="button" className="btn secondary" disabled={!file || busy} onClick={() => upload(false)}>Проверить файл</button>
          {preview && <button type="button" className="btn" disabled={busy || !preview.orders || !!preview.errors.length} onClick={() => upload(true)}>Сохранить продажи</button>}
        </div>
        {busy && <p role="status">Обработка файла…</p>}
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {preview && <>
          <p>К импорту: {preview.orders} заказов, {preview.rows} строк на сумму {preview.revenue} BYN. Повторных строк: {preview.duplicates}. Ошибок: {preview.errors.length}.</p>
          {!!preview.months?.length && !preview.errors.length && (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <caption>Новые продажи по месяцам</caption>
                <thead><tr><th>Месяц</th><th>Заказов</th><th>Выручка, BYN</th></tr></thead>
                <tbody>
                  {preview.months.map(({ month, orders, revenue }) => (
                    <tr key={month}>
                      <td>{monthFormat.format(new Date(`${month}-01T00:00:00Z`))}</td>
                      <td>{orders}</td>
                      <td>{revenue.replace('.', ',')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!!preview.errors.length && <>
            <p>Исправьте ошибки и проверьте файл снова.</p>
            <ul>{preview.errors.slice(0, 20).map(({ line, message }, index) =>
              <li key={index}>Строка {line}: {message}</li>
            )}</ul>
          </>}
        </>}
      </div>
    </section>
  )
}
