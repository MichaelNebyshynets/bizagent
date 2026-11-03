import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Icon, PageHead } from './ui'

// Демо-данные. Потом заменить на ответ инструмента get_sales_summary
const MONTHS = ['ноя', 'дек', 'янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт']
const DATA = MONTHS.map((m, i) => ({ m, v: [39000, 52000, 31000, 34000, 38000, 42000, 40000, 47000, 53000, 56000, 55000, 48320][i] }))

const PRODUCTS = [
  ['Плед флисовый 150x200', 'Текстиль', 7980, 40, 'Не продавался 18 дней'],
  ['Комплект постельного белья', 'Текстиль', 6230, 25],
  ['Кружка керамическая', 'Посуда', 5520, 90],
  ['Свеча ароматическая', 'Декор', 4950, 55],
  ['Набор тарелок 18 предметов', 'Посуда', 4440, 18],
]
const STOCK = [
  ['Гирлянда светодиодная', 2, 'low', 'Сезонный спрос растёт'],
  ['Сковорода 26 см', 3, 'low', 'Хватит примерно на неделю'],
  ['Чайник эмалированный', 4, 'low', 'Хватит примерно на 10 дней'],
  ['Часы настенные ретро', 15, 'stale', 'Нет продаж 45 дней'],
  ['Подсвечник латунный', 12, 'stale', 'Нет продаж 38 дней'],
]
const byn = (v) => v.toLocaleString('ru-RU')

export default function Analytics({ company, onAsk, go }) {
  const [period, setPeriod] = useState(6)
  const rows = DATA.slice(-period)
  const total = rows.reduce((s, r) => s + r.v, 0)

  return (
    <section>
      <PageHead company={company} tab="an" title="Аналитика" sub="Сейчас показаны демо-данные. Чтобы увидеть свои цифры, приложите файл продаж в чате ассистента.">
        <button className="btn secondary" onClick={() => go('chat')}><Icon name="up" />Приложить продажи</button>
        <button className="btn secondary" onClick={() => window.print()}><Icon name="down" />Скачать отчёт PDF</button>
      </PageHead>

      <div className="stack">
        <section className="panel">
          <div className="panel-head">
            <div><h2>Выручка по месяцам, BYN</h2><p>За период: <span className="num">{byn(total)}</span> BYN</p></div>
            <div className="seg" role="group" aria-label="Период">
              {[3, 6, 12].map((p) => (
                <button key={p} className={period === p ? 'on' : ''} onClick={() => setPeriod(p)}>{p} мес</button>
              ))}
            </div>
          </div>
          <div className="panel-body" style={{ height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={rows} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="m" stroke="var(--muted)" tickLine={false} axisLine={false} />
                <YAxis stroke="var(--muted)" tickLine={false} axisLine={false} tickFormatter={(v) => `${v / 1000} тыс`} width={56} />
                <Tooltip cursor={{ fill: 'var(--hover)' }} formatter={(v) => [`${byn(v)} BYN`, 'Выручка']}
                  contentStyle={{ border: '1px solid var(--line)', borderRadius: 8, fontSize: 13 }} />
                <Bar dataKey="v" radius={[4, 4, 0, 0]} maxBarSize={64}>
                  {rows.map((r, i) => <Cell key={r.m} fill={i === rows.length - 1 ? 'var(--acc)' : 'var(--chart)'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="summary">
            <p><b>Что видно:</b> выручка росла до августа, в сентябре остановилась, в октябре упала на 12%. Основная просадка в категории «Текстиль»: плед флисовый не продавался 18 дней, хотя на складе 40 штук.</p>
            <button className="btn" onClick={() => onAsk('Почему упала выручка в октябре и что сделать?')}>Обсудить с ассистентом</button>
          </div>
        </section>

        <div className="cols-2">
          <section className="panel">
            <div className="panel-head"><h2>Товары по выручке за октябрь</h2></div>
            <table>
              <thead><tr><th>Товар</th><th className="r">Выручка</th><th className="r">Остаток</th></tr></thead>
              <tbody>
                {PRODUCTS.map(([name, cat, rev, stock, note]) => (
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
              <button className="btn sm secondary" onClick={() => onAsk('Подготовь заказ поставщику на товары, которые заканчиваются')}>Подготовить заказ</button>
            </div>
            <table>
              <thead><tr><th>Товар</th><th className="r">Остаток</th><th>Статус</th></tr></thead>
              <tbody>
                {STOCK.map(([name, qty, status, note]) => (
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
      </div>
    </section>
  )
}
