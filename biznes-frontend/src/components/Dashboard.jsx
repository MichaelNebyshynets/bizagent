import { useState } from 'react'

const CHIPS = [
  'Почему упала выручка?',
  'Что заканчивается на складе?',
  'Какую форму налогообложения выбрать?',
  'Проверь контрагента по УНП',
]

export default function Dashboard({ onAsk }) {
  const [q, setQ] = useState('')
  return (
    <section>
      <h1>Добрый день, «Уютный дом»</h1>
      <p className="sub">Сводка по вашему бизнесу · демо-данные</p>
      <div className="grid g3">
        <div className="card"><div className="k">Выручка за месяц</div><div className="v">48 320 BYN</div><div className="dn">▼ 12% к прошлому месяцу</div></div>
        <div className="card"><div className="k">Налоговый режим</div><div className="v">УСН</div><div className="src">из профиля бизнеса</div></div>
        <div className="card"><div className="k">Ближайший дедлайн</div><div className="v">через 9 дней</div><div className="src">срок берётся из базы знаний</div></div>
      </div>
      <div className="ai">
        <h2>✦ Спросите ИИ-ассистента</h2>
        <div className="box">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Например: почему упала выручка в сентябре?"
            onKeyDown={(e) => e.key === 'Enter' && q && onAsk(q)} />
          <button className="btn" onClick={() => q && onAsk(q)}>Спросить</button>
        </div>
        <div className="chips">
          {CHIPS.map((c) => <span key={c} className="chip" onClick={() => onAsk(c)}>{c}</span>)}
        </div>
      </div>
      <h2>Инсайты от ИИ</h2>
      <div className="grid g3">
        <div className="card"><span className="tag">Продажи</span><div>Плед флисовый не продавался 18 дней, это главная причина просадки.</div></div>
        <div className="card"><span className="tag">Склад</span><div>3 товара почти закончились, 2 залежались.</div></div>
        <div className="card"><span className="tag">Закон</span><div>Изменения по вашему режиму: ответ только с источником и датой документа.</div></div>
      </div>
    </section>
  )
}
