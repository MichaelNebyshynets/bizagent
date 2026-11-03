import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import Chat from './components/Chat'
import Analytics from './components/Analytics'
import KnowledgeBase from './components/KnowledgeBase'
import Profile from './components/Profile'
import { Login } from './components/Login'
import { Icon, TABS, NextStep } from './components/ui'

const ROLE_RU = { owner: 'Владелец', manager: 'Менеджер', accountant: 'Бухгалтер' }
// Пока бэкенд не отдаёт название компании при входе, берём его по домену email (демо-аккаунты)
const COMPANY_BY_DOMAIN = { 'uyut.by': 'Уютный дом', 'flora.by': 'Флора' }

// Прогресс «Начала работы» хранится в браузере отдельно для каждого пользователя
const ONB_EMPTY = { profile: false, data: false, ask: false }
const onbKey = () => `onboarding_${localStorage.getItem('user_email') || 'user'}`
const loadOnb = () => {
  try { return { ...ONB_EMPTY, ...JSON.parse(localStorage.getItem(onbKey()) || '{}') } } catch { return ONB_EMPTY }
}

export default function App() {
  const [tab, setTab] = useState('dash')
  const [question, setQuestion] = useState('') // вопрос с других вкладок, уходит в чат
  const [menuOpen, setMenuOpen] = useState(false)
  const [toast, setToast] = useState('')

  // Авторизация
  const [token, setToken] = useState(localStorage.getItem('auth_token'))
  const [userName, setUserName] = useState(localStorage.getItem('user_name') || '')
  const [onb, setOnb] = useState(loadOnb)

  const role = ROLE_RU[localStorage.getItem('user_role')] || localStorage.getItem('user_role') || ''
  const email = localStorage.getItem('user_email') || ''
  const company = COMPANY_BY_DOMAIN[email.split('@')[1]] || 'Ваша компания'

  const go = (id) => { setTab(id); setMenuOpen(false); window.scrollTo(0, 0) }
  const ask = (q) => { setQuestion(q); go('chat') }
  const notify = (text) => { setToast(text); setTimeout(() => setToast(''), 2600) }
  const markDone = (step) => setOnb((prev) => {
    if (prev[step]) return prev
    const next = { ...prev, [step]: true }
    localStorage.setItem(onbKey(), JSON.stringify(next))
    return next
  })

  useEffect(() => {
    const close = (e) => e.key === 'Escape' && setMenuOpen(false)
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [])

  const handleLogin = (data) => {
    setToken(data.access_token)
    setUserName(data.name)
    setOnb(loadOnb())
    setTab('dash')
  }

  const handleLogout = () => {
    ;['auth_token', 'user_name', 'user_role', 'user_email'].forEach((k) => localStorage.removeItem(k))
    setToken(null)
    setUserName('')
    setMenuOpen(false)
  }

  // Если пользователь не авторизован — показываем экран входа
  if (!token) {
    return <Login onLogin={handleLogin} />
  }

  // Инициалы для кнопки аватара: «Анна Дорошевич» → «АД»
  const initials = userName
    ? userName.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()
    : '?'

  const common = { company, go, onAsk: ask, notify }

  return (
    <div onClick={() => menuOpen && setMenuOpen(false)}>
      <header className="top">
        <div className="brand"><span className="brand-mark">Б</span>БизнесПомощник <small>РБ</small></div>
        <div className="top-spacer" />
        <div className="company"><span>Компания</span><b>{company}</b></div>
        <button
          className="avatar"
          title={`${userName}, ${role}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v) }}
        >
          {initials}
        </button>
        {menuOpen && (
          <div className="menu" role="menu" onClick={(e) => e.stopPropagation()}>
            <div className="who"><b>{userName}</b><div className="small muted">{role}, {company}</div></div>
            <button onClick={() => go('prof')}>Профиль бизнеса</button>
            <button onClick={handleLogout} style={{ color: 'var(--bad)' }}>Выйти</button>
          </div>
        )}
      </header>

      <div className="tabs">
        <nav aria-label="Разделы">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`${tab === t.id ? 'on' : ''} ${t.settings ? 'settings' : ''}`}
              aria-current={tab === t.id ? 'page' : undefined}
              onClick={() => go(t.id)}
            >
              <Icon name={t.icon} />{t.label}
              {t.id === 'prof' && !onb.profile && <span className="badge" title="Профиль заполнен не полностью">!</span>}
            </button>
          ))}
        </nav>
      </div>

      <main>
        <div className="page">
          {tab === 'dash' && <Dashboard {...common} userName={userName} onb={onb} />}
          {tab === 'an' && <Analytics {...common} />}
          {tab === 'chat' && (
            <Chat
              initial={question}
              clear={() => setQuestion('')}
              company={company}
              onEvent={(e) => markDone(e === 'upload' ? 'data' : 'ask')}
            />
          )}
          {tab === 'kb' && <KnowledgeBase {...common} />}
          {tab === 'prof' && <Profile {...common} role={localStorage.getItem('user_role')} onSaved={(unp) => unp && markDone('profile')} />}
          <NextStep tab={tab} go={go} />
        </div>
      </main>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}
