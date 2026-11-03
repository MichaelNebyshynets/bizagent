import { useState } from 'react'
import { Icon, PageHead } from './ui'

// Список совпадает с документами в bizagent/kb_docs (TITLE, DOC_DATE, SOURCE_URL).
// Потом заменить на запрос к бэкенду, когда появится эндпоинт со списком документов.
const DOCS = [
  ['Налоговый кодекс РБ: глава по УСН (ставки и лимиты)', 'Налоги', '01.01.2026', 'https://pravo.by/document/?guid=3871&p0=H10900071'],
  ['Налог на добавленную стоимость (НДС) в Республике Беларусь', 'Налоги', '01.01.2026', 'https://nalog.gov.by/vat/'],
  ['Порядок выплаты дивидендов учредителям', 'Налоги', '01.01.2026', 'https://nalog.gov.by/faq/dividends/'],
  ['Подоходный налог с физических лиц и налоговые агенты', 'Зарплата и взносы', '01.01.2026', 'https://nalog.gov.by/income_tax/'],
  ['Правила уплаты страховых взносов в ФСЗН для ИП и ООО', 'Зарплата и взносы', '01.01.2026', 'https://ssf.gov.by/ru/ispl-vznos-ip-ru/'],
  ['Государственная статистическая отчётность малого бизнеса', 'Касса и отчётность', '01.01.2026', 'https://www.belstat.gov.by/'],
  ['Кассовое оборудование и средства контроля налоговых органов (СКНО)', 'Касса и отчётность', '01.01.2025', 'https://nbrb.by/legislation/'],
  ['Законодательство об индивидуальной предпринимательской деятельности', 'Открытие и работа ИП', '01.10.2025', 'https://pravo.by/document/?guid=12551&p0=H12400365'],
  ['Валютное регулирование и расчёты во внешнеэкономической деятельности', 'ВЭД', '01.07.2025', 'https://nbrb.by/regulations/forex/'],
  ['Трудовые отношения и заключение контрактов (ТК РБ)', 'Трудовые отношения', '01.01.2025', 'https://pravo.by/document/?guid=3871&p0=H19900296'],
]
const CATS = ['Все', ...new Set(DOCS.map((d) => d[1]))]
const host = (url) => new URL(url).hostname.replace('www.', '')

export default function KnowledgeBase({ company, onAsk }) {
  const [cat, setCat] = useState('Все')
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')

  const q = query.trim().toLowerCase()
  const docs = DOCS.filter(([title, c]) => (cat === 'Все' || c === cat) && (!q || title.toLowerCase().includes(q)))

  return (
    <section>
      <PageHead company={company} tab="kb" title="База знаний" sub="Документы по налогам и праву РБ. Ассистент отвечает только по ним и всегда указывает источник." />

      <div className="stack">
        <div className="notice">Это справочная информация по официальным документам, а не юридическая консультация. Перед важным решением сверьтесь с актуальной редакцией.</div>

        <form className="search" onSubmit={(e) => { e.preventDefault(); setQuery(draft) }}>
          <input className="input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Поиск по документам: УСН, ФСЗН, касса…" aria-label="Поиск по документам" />
          <button className="btn" type="submit">Найти</button>
        </form>

        <div className="chips">
          {CATS.map((c) => <button key={c} className={`chip ${cat === c ? 'on' : ''}`} onClick={() => setCat(c)}>{c}</button>)}
        </div>

        <section className="panel">
          <div className="panel-head"><h2>Документы</h2><span className="small muted">{docs.length} из {DOCS.length}</span></div>
          {docs.length ? docs.map(([title, c, date, url]) => (
            <div className="doc" key={title}>
              <div className="t">
                <h3>{title}</h3>
                <div className="meta"><span className="pill">{c}</span><span>Редакция от {date}</span><span>Источник: {host(url)}</span></div>
              </div>
              <div className="acts">
                <a className="btn sm ghost" href={url} target="_blank" rel="noopener noreferrer"><Icon name="ext" />Открыть</a>
                <button className="btn sm secondary" onClick={() => onAsk(`Объясни коротко, что важно для нас в документе: ${title}`)}>Спросить по документу</button>
              </div>
            </div>
          )) : (
            <div className="panel-body">
              <p><b>Ничего не нашлось по запросу «{query}».</b></p>
              <p className="muted" style={{ marginTop: 4 }}>Попробуйте другое слово или задайте вопрос ассистенту: если документа нет в базе, он так и ответит.</p>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><div><h2>Меры господдержки</h2><p>Льготные кредиты, гранты, налоговые льготы</p></div></div>
          <div className="panel-body">
            <p><b>Документы о мерах поддержки ещё не загружены.</b></p>
            <p className="muted" style={{ marginTop: 4 }}>Когда они появятся, здесь будет таблица мер с условиями и ссылками. До этого ассистент не отвечает на такие вопросы по памяти.</p>
          </div>
        </section>
      </div>
    </section>
  )
}
