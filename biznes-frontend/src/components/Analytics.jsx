import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Icon, PageHead } from './ui'
import { useOverview } from '../useOverview'

const byn = (v) => v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('ru-RU', { notation: 'compact', maximumFractionDigits: 1 })
const fullMonth = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' })

export default function Analytics({ company, onAsk, go, canPurchase }) {
  const [period, setPeriod] = useState(6)
  const [metric, setMetric] = useState('revenue')
  const showRevenue = metric === 'revenue'
  const { data, error } = useOverview()
  const MN = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
  const [year, month] = (data?.today ?? '').split('-').map(Number)
  const start = year * 12 + month - period
  const sales = new Map(data?.months.map((group) => [group.key, group]))
  const rows = data ? Array.from({ length: period }, (_, index) => {
    const offset = start + index
    const monthIndex = offset % 12
    const key = `${Math.floor(offset / 12)}-${String(monthIndex + 1).padStart(2, '0')}`
    const group = sales.get(key)
    return { key, label: `${MN[monthIndex]} ${key.slice(2, 4)}`, revenue: group?.revenue ?? 0, orders: group?.orders ?? 0 }
  }) : []
  const orders = rows.reduce((count, row) => count + row.orders, 0)
  const products = data ? data.top_products.map((p) => [p.name, '', p.revenue, `${p.quantity} шт`]) : []
  const stockRows = data
    ? [...data.low_stock.map((p) => [p.name, p.stock, 'low', 'Мало на складе']),
       ...data.slow_movers.map((p) => [p.name, p.stock, 'stale', p.days_since_last_sale ? `Нет продаж ${p.days_since_last_sale} дн.` : 'Не продавался'])]
    : []
  const ch = data?.month.revenue_change_pct
  const summary = !data ? null : ch == null
    ? 'Для сравнения с прошлым месяцем пока мало данных.'
    : ch === 0 ? 'Выручка за текущий месяц совпадает с прошлым за то же число дней.'
    : `Выручка за текущий месяц ${ch > 0 ? 'выше' : 'ниже'} прошлого на ${Math.abs(ch)}% (за то же число дней).`
  const total = rows.reduce((s, r) => s + r.revenue, 0)

  return (
    <section>
      <PageHead company={company} tab="an" title="Аналитика" sub="Продажи и остатки из базы компании">
        <button className="btn secondary" onClick={() => window.print()}><Icon name="down" />Скачать отчёт PDF</button>
      </PageHead>

      <div className="stack">
        {error && <p role="alert">Не удалось загрузить аналитику. {error}</p>}
        {!data && !error && <p role="status">Загрузка аналитики…</p>}
        {data && !error && <>
        <section className="panel">
          <div className="panel-head">
            <div><h2>{showRevenue ? 'Выручка по месяцам, BYN' : 'Заказы по месяцам'}</h2><p>За период: <span className="num">{byn(total)}</span> BYN · {orders} заказов</p></div>
            <div className="seg" role="group" aria-label="Показатель">
              <button aria-pressed={showRevenue} className={showRevenue ? 'on' : ''} onClick={() => setMetric('revenue')}>Выручка</button>
              <button aria-pressed={!showRevenue} className={!showRevenue ? 'on' : ''} onClick={() => setMetric('orders')}>Заказы</button>
            </div>
            <div className="seg" role="group" aria-label="Период">
              {[3, 6, 12].map((p) => (
                <button key={p} aria-pressed={period === p} className={period === p ? 'on' : ''} onClick={() => setPeriod(p)}>{p} мес</button>
              ))}
            </div>
          </div>
          {orders > 0 ? <div className="panel-body" style={{ height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={rows} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="key" tickFormatter={(key) => rows.find((row) => row.key === key)?.label} stroke="var(--muted)" tickLine={false} axisLine={false} />
                <YAxis stroke="var(--muted)" tickLine={false} axisLine={false} allowDecimals={showRevenue} tickFormatter={(v) => compact.format(v)} width={56} />
                <Tooltip cursor={{ fill: 'var(--hover)' }} labelFormatter={(key) => fullMonth.format(new Date(`${key}-01T00:00:00Z`))}
                  formatter={(v) => showRevenue ? [`${byn(v)} BYN`, 'Выручка'] : [v.toLocaleString('ru-RU'), 'Заказы']}
                  contentStyle={{ border: '1px solid var(--line)', borderRadius: 8, fontSize: 13 }} />
                <Bar dataKey={metric} radius={[4, 4, 0, 0]} maxBarSize={64}>
                  {rows.map((r, i) => <Cell key={r.key} fill={i === rows.length - 1 ? 'var(--acc)' : 'var(--chart)'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div> : <p className="panel-body">Нет продаж за выбранный период.</p>}
          {orders > 0 && <>
            <details className="panel-body">
              <summary>Данные по месяцам</summary>
              <table>
                <thead><tr><th>Месяц</th><th className="r">Выручка, BYN</th><th className="r">Заказы</th></tr></thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.key}>
                      <td>{fullMonth.format(new Date(`${row.key}-01T00:00:00Z`))}{row.key === data.today.slice(0, 7) && ' (текущий)'}</td>
                      <td className="r num">{byn(row.revenue)}</td>
                      <td className="r num">{row.orders}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
            <div className="summary">
              <p>{summary}</p>
              <button className="btn" onClick={() => onAsk(
                `Проанализируй ${showRevenue ? 'выручку' : 'количество заказов'} по месяцам за период с ${rows[0].key}-01 по ${data.today}. Выдели самое заметное изменение, предложи вероятные причины, объясни, как их проверить, и скажи, что сделать первым.`
              )}>Обсудить с ассистентом</button>
            </div>
          </>}
        </section>

        <div className="cols-2">
          <section className="panel">
            <div className="panel-head"><h2>Товары по выручке за 3 месяца</h2></div>
            <table>
              <thead><tr><th>Товар</th><th className="r">Выручка</th><th className="r">Продано</th></tr></thead>
              <tbody>
                {products.map(([name, cat, rev, stock, note]) => (
                  <tr key={name}>
                    <td>{name}<div className="small muted">{cat}{note && <>. <span className="down">{note}</span></>}</div></td>
                    <td className="r num">{byn(rev)}</td>
                    <td className="r num">{stock}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2>Склад: что сделать</h2>
              <button className="btn sm secondary" onClick={() => onAsk('Какие товары заканчиваются и сколько стоит докупить? Дай рекомендации по закупке.')}>Что докупить</button>
              {canPurchase && <button className="btn sm secondary" onClick={() => go('purchases')}>Закупки</button>}
            </div>
            <table>
              <thead><tr><th>Товар</th><th className="r">Остаток</th><th>Статус</th></tr></thead>
              <tbody>
                {stockRows.map(([name, qty, status, note]) => (
                  <tr key={name}>
                    <td>{name}<div className="small muted">{note}</div></td>
                    <td className="r num">{qty} шт</td>
                    <td>{status === 'low' ? <span className="pill bad">Заканчивается</span> : <span className="pill warn">Залежался</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
        </>}
      </div>
    </section>
  )
}
