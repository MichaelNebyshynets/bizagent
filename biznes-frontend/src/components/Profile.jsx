import { useState } from 'react'
import { PageHead } from './ui'

// Эндпоинта для профиля на бэкенде пока нет: анкета сохраняется в браузере.
// Когда появится (таблица companies), заменить load/save на запросы к API.
const DEFAULTS = {
  'Уютный дом': { name: 'Уютный дом', unp: '', form: 'ИП', regime: 'УСН', activity: 'Розничная торговля товарами для дома', city: 'Минск', staff: '6' },
  'Флора': { name: 'Флора', unp: '', form: 'ООО', regime: 'Общий', activity: 'Цветочный магазин', city: 'Гомель', staff: '3' },
}
const EMPTY = { name: '', unp: '', form: 'ИП', regime: 'УСН', activity: '', city: '', staff: '' }
const FIELDS = ['name', 'unp', 'form', 'regime', 'activity', 'city', 'staff']
const ROLES = [
  ['Владелец', 'Всё, включая профиль и журнал действий ассистента'],
  ['Менеджер', 'Клиенты и заказы'],
  ['Бухгалтер', 'Расходы и отчёты'],
]

const key = (company) => `profile_${company}`
const load = (company) => {
  try { return { ...EMPTY, ...(DEFAULTS[company] || {}), ...JSON.parse(localStorage.getItem(key(company)) || '{}') } }
  catch { return { ...EMPTY, ...(DEFAULTS[company] || {}) } }
}

export default function Profile({ company, role, notify, onSaved }) {
  const [saved, setSaved] = useState(() => load(company))
  const [form, setForm] = useState(saved)
  const canEdit = role === 'owner'

  const filled = FIELDS.filter((f) => String(form[f] || '').trim()).length
  const unpBad = form.unp !== '' && !/^\d{9}$/.test(form.unp)
  const dirty = JSON.stringify(form) !== JSON.stringify(saved)
  const set = (f) => (e) => setForm((prev) => ({ ...prev, [f]: e.target.value }))

  const save = () => {
    localStorage.setItem(key(company), JSON.stringify(form))
    setSaved(form)
    onSaved?.(form.unp)
    notify('Изменения сохранены')
  }

  const Field = ({ id, label, hint, wide, children }) => (
    <div className="field" style={wide ? { gridColumn: '1 / -1' } : undefined}>
      <label htmlFor={`f_${id}`}>{label}</label>
      {children}
      {hint}
    </div>
  )
  const input = (f, props = {}) => (
    <input id={`f_${f}`} className={`input ${f === 'unp' && unpBad ? 'invalid' : ''}`} value={form[f]} onChange={set(f)} disabled={!canEdit} {...props} />
  )
  const select = (f, options) => (
    <select id={`f_${f}`} className="input" value={form[f]} onChange={set(f)} disabled={!canEdit}>
      {options.map((o) => <option key={o}>{o}</option>)}
    </select>
  )

  return (
    <section>
      <PageHead company={company} tab="prof" title="Профиль бизнеса" sub="От этих данных зависят ответы ассистента: ставки налогов, сроки отчётов, проверки контрагентов." />

      <div className="stack">
        <section className="panel"><div className="panel-body">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
            <b>Заполнено {filled} из {FIELDS.length} полей</b>
            {!form.unp && <span className="small muted">Не хватает УНП: без него ассистент не проверит контрагентов и сроки</span>}
          </div>
          <div className="progress"><i style={{ width: `${(filled / FIELDS.length) * 100}%` }} /></div>
        </div></section>

        {!canEdit && <div className="notice">Изменять профиль может только владелец. Вы можете посмотреть данные.</div>}

        <form className="panel" onSubmit={(e) => { e.preventDefault(); if (canEdit && dirty && !unpBad) save() }}>
          <div className="form-sec">
            <div className="lead"><h2>Компания</h2><p>Как в свидетельстве о регистрации</p></div>
            <div className="form-grid">
              {Field({ id: 'name', label: 'Название', children: input('name') })}
              {Field({
                id: 'unp', label: 'УНП',
                children: input('unp', { inputMode: 'numeric', maxLength: 9, placeholder: '9 цифр' }),
                hint: unpBad ? <div className="err">УНП состоит ровно из 9 цифр</div> : <div className="hint">Есть в свидетельстве о госрегистрации</div>,
              })}
              {Field({ id: 'form', label: 'Форма', children: select('form', ['ИП', 'ООО', 'ЧУП', 'ОДО']) })}
              {Field({ id: 'regime', label: 'Налоговый режим', children: select('regime', ['УСН', 'Общий', 'Единый налог']) })}
            </div>
          </div>
          <div className="form-sec">
            <div className="lead"><h2>Деятельность</h2><p>Нужно для сравнения с отраслью и подсказок по мерам поддержки</p></div>
            <div className="form-grid">
              {Field({ id: 'activity', label: 'Основной вид деятельности', wide: true, children: input('activity') })}
              {Field({ id: 'city', label: 'Город', children: input('city') })}
              {Field({ id: 'staff', label: 'Сотрудников', children: input('staff', { inputMode: 'numeric' }) })}
            </div>
          </div>
          <div className="form-sec">
            <div className="lead"><h2>Доступ</h2><p>Какие роли есть в системе и что они могут делать</p></div>
            <div className="panel">
              <table>
                <thead><tr><th>Роль</th><th>Права</th></tr></thead>
                <tbody>{ROLES.map(([r, rights]) => <tr key={r}><td>{r}</td><td className="small">{rights}</td></tr>)}</tbody>
              </table>
            </div>
          </div>
        </form>

        {canEdit && dirty && (
          <div className="savebar">
            <span>Есть несохранённые изменения</span>
            <div className="actions">
              <button className="btn ghost" onClick={() => setForm(saved)}>Отменить</button>
              <button className="btn" onClick={save} disabled={unpBad}>Сохранить изменения</button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
