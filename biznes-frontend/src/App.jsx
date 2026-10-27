import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import Chat from './components/Chat'
import Analytics from './components/Analytics'
import KnowledgeBase from './components/KnowledgeBase'
import Profile from './components/Profile'
import { Login } from './components/Login'

const TABS = [
  ['dash', '◧ Дашборд'],
  ['chat', '✦ ИИ-ассистент'],
  ['an', '▤ Аналитика'],
  ['kb', '☰ База знаний'],
  ['prof', '⚙ Профиль бизнеса'],
]

export default function App() {
  const [tab, setTab] = useState('dash')
  const [question, setQuestion] = useState('') // вопрос с дашборда, уходит в чат
  
  // Авторизация
  const [token, setToken] = useState(localStorage.getItem('auth_token'))
  const [userName, setUserName] = useState(localStorage.getItem('user_name') || 'УД')

  const ask = (q) => { setQuestion(q); setTab('chat') }

  const handleLogin = (data) => {
    setToken(data.access_token)
    setUserName(data.name)
  }

  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_name')
    localStorage.removeItem('user_role')
    setToken(null)
    setUserName('')
  }

  // Если пользователь не авторизован — показываем экран логина
  if (!token) {
    return <Login onLogin={handleLogin} />
  }

  // Получаем короткие инициалы для кнопки аватара (например, "Владелец" -> "ВЛ")
  const initials = userName
    ? userName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'УД'

  return (
    <>
      <header>
        <div className="logo">Бизнес<b>Помощник</b> · РБ</div>
        <nav>
          <span style={{ marginRight: '15px', color: '#666', fontSize: '14px' }}>
            {userName}
          </span>
          <a href="#" onClick={(e) => { e.preventDefault(); handleLogout(); }} style={{ color: '#ff4d4d' }}>
            Выйти
          </a>
        </nav>
        <button className="avatar" title={`Профиль: ${userName}`} onClick={() => setTab('prof')}>
          {initials}
        </button>
      </header>
      <div className="layout">
        <aside>
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </aside>
        <main>
          {tab === 'dash' && <Dashboard onAsk={ask} />}
          {tab === 'chat' && <Chat initial={question} clear={() => setQuestion('')} />}
          {tab === 'an' && <Analytics />}
          {tab === 'kb' && <KnowledgeBase />}
          {tab === 'prof' && <Profile onLogout={handleLogout} />}
        </main>
      </div>
    </>
  )
}