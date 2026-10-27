import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Демо-данные. Потом заменить на ответ инструмента get_sales_summary
const DATA = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт'].map((m, i) => ({
  m, v: [31, 34, 38, 42, 40, 47, 53, 56, 55, 48][i] * 1000,
}))

export default function Analytics() {
  return (
    <section>
      <h1>Аналитика</h1>
      <p className="sub">Графики по данным компании</p>
      <div className="card">
        <div className="head">
          <h2>Выручка по месяцам, BYN</h2>
          <button className="btn ghost" disabled>Загрузить CSV</button>
          <button className="btn" onClick={() => window.print()}>Отчёт PDF</button>
        </div>
        <div style={{ height: 260 }}>
          <ResponsiveContainer>
            <AreaChart data={DATA}>
              <CartesianGrid stroke="#30353e" vertical={false} />
              <XAxis dataKey="m" stroke="#8f96a3" /><YAxis stroke="#8f96a3" />
              <Tooltip contentStyle={{ background: '#1f2228', border: '1px solid #30353e' }} />
              <Area dataKey="v" stroke="#4a8fe7" fill="#3b82e6" fillOpacity={0.12} strokeWidth={2.5} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="card inner">✦ <b>Вывод ИИ:</b> выручка росла до августа, затем просела на 12%. Проверьте наличие ходового товара и закупки.</div>
      </div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card"><h2>Мы vs отрасль</h2><div className="src">Появится после подключения данных Белстата.</div></div>
        <div className="card"><h2>ИИ-советы по развитию</h2><div className="src">Рекомендации строятся на ваших продажах и складе.</div></div>
      </div>
    </section>
  )
}
