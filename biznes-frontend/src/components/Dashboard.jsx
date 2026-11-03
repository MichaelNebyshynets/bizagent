import { useState } from 'react'
import { PageHead } from './ui'

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
      <PageHead company={company} tab="dash" title={name ? `Добрый день, ${name}` : 'Добрый день'} sub={`${company}. Сводка за октябрь 2026, демо-данные.`}>
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

        <section className="panel stats">
          <div className="stat"><div className="k">Выручка за октябрь</div><div className="v num">48 320 BYN</div><div className="d down">−12% к сентябрю</div></div>
          <div className="stat"><div className="k">Валовая прибыль</div><div className="v num">19 870 BYN</div><div className="d muted">Маржа 41%</div></div>
          <div className="stat"><div className="k">Средний чек</div><div className="v num">41,20 BYN</div><div className="d up">+3% к сентябрю</div></div>
          <div className="stat"><div className="k">Ближайший срок</div><div className="v">20 ноября</div><div className="d muted">Декларация по УСН</div></div>
        </section>

        <div className="cols">
          <section className="panel">
            <div className="panel-head"><div><h2>Требует внимания</h2><p>Отсортировано по срочности</p></div></div>
            <ul className="todo">
              <li><span className="dot bad" /><div className="t"><b>Заканчиваются 3 товара</b><p>Гирлянда (2 шт), сковорода 26 см (3 шт), чайник (4 шт).</p></div>
                <button className="btn sm secondary" onClick={() => onAsk('Что заканчивается на складе и сколько докупить?')}>Рассчитать закупку</button></li>
              <li><span className="dot bad" /><div className="t"><b>Выручка упала на 12% к сентябрю</b><p>Главная причина: плед флисовый не продавался 18 дней.</p></div>
                <button className="btn sm secondary" onClick={() => go('an')}>Открыть аналитику</button></li>
              <li><span className="dot" /><div className="t"><b>2 товара залежались</b><p>Часы настенные ретро и подсвечник латунный: нет продаж больше месяца.</p></div>
                <button className="btn sm secondary" onClick={() => onAsk('Какие товары залежались и что с ними делать?')}>Спросить, что делать</button></li>
            </ul>
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
