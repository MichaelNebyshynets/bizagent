export default function KnowledgeBase() {
  return (
    <section>
      <h1>База знаний и меры поддержки</h1>
      <p className="sub">Каждый ответ со ссылкой на документ и датой редакции</p>
      <div className="box" style={{ marginBottom: 14 }}>
        <input placeholder="Хочу открыть кофейню в Гомеле…" /><button className="btn">Найти</button>
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Мера</th><th>Тип</th><th>Источник</th></tr></thead>
          <tbody>
            <tr><td>Пример: льготное кредитование</td><td>Кредит</td><td>документ, дата</td></tr>
            <tr><td>Пример: налоговые льготы</td><td>Налоги</td><td>документ, дата</td></tr>
          </tbody>
        </table>
        <div className="src">Строки-примеры. Реальные данные только из загруженных документов, иначе агент отвечает «не нашёл».</div>
      </div>
    </section>
  )
}
