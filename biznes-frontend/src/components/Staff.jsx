import { useEffect, useState } from 'react'
import { workflowApi } from '../workflowApi'
import { PageHead } from './ui'

const roles = { owner: 'Владелец', manager: 'Менеджер', accountant: 'Бухгалтер' }
const blank = { email: '', name: '', password: '', role: 'manager' }

function RoleSelect({ value, onChange }) {
  return <select className="input" aria-label="Роль" value={value} onChange={(e) => onChange(e.target.value)}>
    {Object.entries(roles).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
  </select>
}

function StaffRow({ member, own, onSave }) {
  const [role, setRole] = useState(member.role)
  const [active, setActive] = useState(member.active)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    try {
      await onSave(member.id, { role, active })
    } finally {
      setBusy(false)
    }
  }

  return <tr>
    <td>{member.name}{own && ' (вы)'}</td><td>{member.email}</td>
    <td>{own ? roles[member.role] : <RoleSelect value={role} onChange={setRole} />}</td>
    <td>{own ? 'Активен' : <label><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Доступ разрешён</label>}</td>
    <td>{!own && <button type="button" className="btn sm secondary"
      disabled={busy || (role === member.role && active === member.active)} onClick={save}>Сохранить</button>}</td>
  </tr>
}

export default function Staff({ company, currentEmail }) {
  const [items, setItems] = useState(null)
  const [form, setForm] = useState(blank)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    workflowApi('/staff', { signal: controller.signal }).then(setItems).catch((cause) => {
      if (!controller.signal.aborted) setError(cause.message)
    })
    return () => controller.abort()
  }, [])

  async function add(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const member = await workflowApi('/staff', { method: 'POST', body: form })
      setItems((previous) => [...previous, member])
      setForm(blank)
    } catch (cause) {
      setError(cause.message)
    } finally {
      setBusy(false)
    }
  }

  async function update(id, body) {
    setError('')
    try {
      const member = await workflowApi(`/staff/${id}`, { method: 'PATCH', body })
      setItems((previous) => previous.map((item) => item.id === id ? member : item))
    } catch (cause) {
      setError(cause.message)
    }
  }

  return <section>
    <PageHead company={company} tab="staff" title="Сотрудники" />
    <div className="stack">
      {error && <p role="alert">{error}</p>}
      {!items && !error && <p role="status">Загрузка…</p>}
      {items && <>
        <section className="panel">
          <div className="panel-head"><h2>Доступ к компании</h2></div>
          <div style={{ overflowX: 'auto' }}><table>
            <thead><tr><th>Имя</th><th>Email</th><th>Роль</th><th>Доступ</th><th>Действие</th></tr></thead>
            <tbody>{items.map((member) => <StaffRow key={member.id} member={member}
              own={member.email.toLowerCase() === currentEmail.toLowerCase()} onSave={update} />)}</tbody>
          </table></div>
        </section>
        <section className="panel">
          <div className="panel-head"><h2>Добавить сотрудника</h2></div>
          <form className="panel-body stack" onSubmit={add}>
            <label>Имя<input className="input" required maxLength={255} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label>Email<input className="input" required type="email" maxLength={255} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
            <label>Роль<RoleSelect value={form.role} onChange={(role) => setForm({ ...form, role })} /></label>
            <label>Начальный пароль<input className="input" required type="password" autoComplete="new-password"
              minLength={12} maxLength={128} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
            <div><button className="btn" disabled={busy}>Создать аккаунт</button></div>
          </form>
        </section>
      </>}
    </div>
  </section>
}
