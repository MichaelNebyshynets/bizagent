import { useState } from 'react'
import { PageHead } from './ui'
import { useOverview } from '../useOverview'

// Демо-данные. Потом заменить на ответы инструментов get_sales_summary, list_low_stock и дедлайны из базы знаний
const QUICK = [
  ['Почему упала выручка?', 'Почему упала выручка в октябре?'],
  ['Налоги в ноябре', 'Какие налоги и взносы платить в ноябре?'],
  ['Проверить контрагента', 'Проверь контрагента по УНП 000000101'],
]

// «Анна Дорошевич» → «Анна»; демо-имена вида «Владелец (Уютный дом)» не подставляем
const firstName = (name) => (name && !/[(,]/.test(name) ? name.split(' ')[0] : '')

export default function Dashboard({ company, userName, onb, go, onAsk }) {
  const [q, setQ] = useState('')
  const [hidden, setHidden] = useState(false)
  const done = Object.values(onb).filter(Boolean).length
  const name = firstName(userName)
  const { data } = useOverview()
  const n = (v) => Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
  const pct = (v) => (v == null ? 'нет данных для сравнения' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)}% к прошлому месяцу`)
  const tone = (v) => (v == null || v === 0 ? 'muted' : v > 0 ? 'up' : 'down')
  const m = data?.month
  const todo = []
  if (data) {
    if (data.low_stock.length) todo.push({ bad: true, title: `Заканчиваются товары: ${data.low_stock.length}`, text: data.low_stock.map((p) => `${p.name} (${p.stock} шт)`).join(', ') + '.', btn: 'Рассчитать закупку', q: 'Что заканчивается на складе и сколько докупить?' })
    if (m.revenue_change_pct != null && m.revenue_change_pct <= -5) todo.push({ bad: true, title: `Выручка ниже на ${Math.abs(m.revenue_change_pct)}% к прошлому месяцу`, text: 'Сравнение за то же число дней.', btn: 'Открыть аналитику', to: 'an' })
    if (data.slow_movers.length) todo.push({ title: `Залежались товары: ${data.slow_movers.length}`, text: data.slow_movers.map((p) => p.name).join(', ') + '. Нет продаж больше месяца.', btn: 'Спросить, что делать', q: 'Какие товары залежались и что с ними делать?' })
  }

  const Step = ({ id, n, title, text, btn, to }) => (
    <li className={`step ${onb[id] ? 'done' : ''}`}>
      <span className="n">{onb[id] ? '✓' : n}</span>
      <b>{title}</b>
      <p>{text}</p>
      {onb[id]
        ? <span className="small" style={{ color: 'var(--good)' }}>Готово</span>
        : <button className="btn sm" onClick={() => go(to)}>{btn}</button>}
    </li>
  )

  return (
    <section>
      <PageHead company={company} tab="dash" title={name ? `Добрый день, ${name}` : 'Добрый день'} sub={data ? `${company}. Сводка на ${new Date(data.today).toLocaleDateString('ru-RU')}.` : `${company}. Сводка за октябрь 2026, демо-данные.`}>
        <button className="btn" onClick={() => go('chat')}>Спросить ассистента</button>
      </PageHead>

      <div className="stack">
        {!hidden && done < 3 && (
          <section className="panel onb">
            <div className="onb-top">
              <div>
                <h2>Начало работы</h2>
                <p className="muted small">Три шага, чтобы ассистент отвечал по вашим данным. Выполнено {done} из 3.</p>
              </div>
              <button className="btn ghost sm" onClick={() => setHidden(true)}>Скрыть</button>
            </div>
            <div className="progress"><i style={{ width: `${(done / 3) * 100}%` }} /></div>
            <ol className="steps">
              <Step id="profile" n={1} title="Заполните профиль" text="УНП, форма и налоговый режим. Без них ассистент не знает ваших сроков и ставок." btn="Заполнить профиль" to="prof" />
              <Step id="data" n={2} title="Загрузите продажи" text="Приложите файл CSV или Excel из кассы или 1С в чате ассистента." btn="Приложить файл" to="chat" />
              <Step id="ask" n={3} title="Задайте первый вопрос" text="Например, почему упала выручка. Ассистент покажет, какие данные смотрел." btn="Открыть ассистента" to="chat" />
            </ol>
          </section>
        )}

        {data ? (
          <section className="panel stats">
            <div className="stat"><div className="k">Выручка за месяц</div><div className="v num">{n(m.revenue)} BYN</div><div className={`d ${tone(m.revenue_change_pct)}`}>{pct(m.revenue_change_pct)}</div></div>
            <div className="stat"><div className="k">Заказов за месяц</div><div className="v num">{m.orders}</div><div className="d muted">Прошлый месяц, то же число дней: {n(m.revenue_prev)} BYN</div></div>
            <div className="stat"><div className="k">Средний чек</div><div className="v num">{n(m.avg_check)} BYN</div><div className={`d ${tone(m.avg_check_change_pct)}`}>{pct(m.avg_check_change_pct)}</div></div>
            {data.profit
              ? <div className="stat"><div className="k">Валовая прибыль</div><div className="v num">{n(data.profit.gross_profit)} BYN</div><div className="d muted">{data.profit.margin_pct != null ? `Маржа ${data.profit.margin_pct}%` : 'Нет продаж'}</div></div>
              : <div className="stat"><div className="k">Товаров мало на складе</div><div className="v num">{data.low_stock.length}</div><div className="d muted">Остаток не больше 5 шт</div></div>}
          </section>
        ) : (
        <section className="panel stats">
          <div className="stat"><div className="k">Выручка за октябрь</div><div className="v num">48 320 BYN</div><div className="d down">−12% к сентябрю</div></div>
          <div className="stat"><div className="k">Валовая прибыль</div><div className="v num">19 870 BYN</div><div className="d muted">Маржа 41%</div></div>
          <div className="stat"><div className="k">Средний чек</div><div className="v num">41,20 BYN</div><div className="d up">+3% к сентябрю</div></div>
          <div className="stat"><div className="k">Ближайший срок</div><div className="v">20 ноября</div><div className="d muted">Декларация по УСН</div></div>
        </section>
        )}

        <div className="cols">
          <section className="panel">
            <div className="panel-head"><div><h2>Требует внимания</h2><p>Отсортировано по срочности</p></div></div>
            {data ? (
              <ul className="todo">
                {todo.length === 0 && <li><span className="dot" /><div className="t"><b>Срочных проблем нет</b><p>Склад и продажи в норме.</p></div></li>}
                {todo.map((t) => (
                  <li key={t.title}><span className={`dot ${t.bad ? 'bad' : ''}`} /><div className="t"><b>{t.title}</b><p>{t.text}</p></div>
                    <button className="btn sm secondary" onClick={() => (t.to ? go(t.to) : onAsk(t.q))}>{t.btn}</button></li>
                ))}
              </ul>
            ) : (
            <ul className="todo">
              <li><span className="dot bad" /><div className="t"><b>Заканчиваются 3 товара</b><p>Гирлянда (2 шт), сковорода 26 см (3 шт), чайник (4 шт).</p></div>
                <button className="btn sm secondary" onClick={() => onAsk('Что заканчивается на складе и сколько докупить?')}>Рассчитать закупку</button></li>
              <li><span className="dot bad" /><div className="t"><b>Выручка упала на 12% к сентябрю</b><p>Главная причина: плед флисовый не продавался 18 дней.</p></div>
                <button className="btn sm secondary" onClick={() => go('an')}>Открыть аналитику</button></li>
              <li><span className="dot" /><div className="t"><b>2 товара залежались</b><p>Часы настенные ретро и подсвечник латунный: нет продаж больше месяца.</p></div>
                <button className="btn sm secondary" onClick={() => onAsk('Какие товары залежались и что с ними делать?')}>Спросить, что делать</button></li>
            </ul>
            )}
          </section>

          <section className="panel">
            <div className="panel-head"><div><h2>Быстрый вопрос</h2><p>Ответ откроется в разделе «Ассистент»</p></div></div>
            <div className="panel-body">
              <form className="stack" style={{ gap: 10 }} onSubmit={(e) => { e.preventDefault(); q.trim() && onAsk(q.trim()) }}>
                <textarea className="input" rows={3} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Например: какие налоги заплатить в ноябре?" aria-label="Вопрос ассистенту" />
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}><button className="btn" type="submit" disabled={!q.trim()}>Спросить</button></div>
              </form>
              <div className="small muted" style={{ margin: '14px 0 8px' }}>Часто спрашивают</div>
              <div className="chips">
                {QUICK.map(([label, text]) => <button key={label} className="chip" onClick={() => onAsk(text)}>{label}</button>)}
              </div>
            </div>
          </section>
        </div>
      </div>
    </section>
  )
}
