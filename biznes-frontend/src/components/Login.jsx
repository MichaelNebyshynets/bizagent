import { useState } from 'react'

const DEMO = [
  ['owner@uyut.by', 'Владелец, Уютный дом'],
  ['manager@uyut.by', 'Менеджер, Уютный дом'],
  ['accountant@uyut.by', 'Бухгалтер, Уютный дом'],
  ['owner@flora.by', 'Владелец, Флора'],
]

export function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const login = async (value) => {
    const address = value.trim()
    if (!/^\S+@\S+\.\S+$/.test(address)) {
      setError('Введите email в формате name@company.by')
      return
    }
    setError('')
    setLoading(true)
    try {
      const response = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: address }),
      })
      let data = await response.json()
      // Бэкенд в режиме mock (без Postgres) отвечает 503: для демо-аккаунтов входим по демо-токену
      if (response.status === 503 && DEMO.some(([a]) => a === address.toLowerCase())) {
        const [user, domain] = address.toLowerCase().split('@')
        const role = user // owner / manager / accountant
        data = { access_token: `demo-${role}-${domain.split('.')[0]}`, role, name: DEMO.find(([a]) => a === address.toLowerCase())[1] }
      } else if (!response.ok) {
        throw new Error(data.detail || 'Такого пользователя нет. Проверьте адрес или войдите через демо-аккаунт.')
      }
      localStorage.setItem('auth_token', data.access_token)
      localStorage.setItem('user_name', data.name)
      localStorage.setItem('user_role', data.role)
      localStorage.setItem('user_email', address.toLowerCase())
      onLogin(data)
    } catch (err) {
      console.error('Login error:', err)
      setError(err.message === 'Failed to fetch'
        ? 'Сервер не отвечает. Проверьте, что бэкенд запущен на порту 8000.'
        : err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login">
      <div className="login-side">
        <div className="brand"><span className="brand-mark">Б</span>БизнесПомощник</div>
        <div>
          <h2>Учёт, цифры и законы для малого бизнеса в Беларуси</h2>
          <ol>
            <li><span className="tick">1</span><div><b>Заполните профиль компании</b><span>УНП, форма и налоговый режим. От них зависят ответы.</span></div></li>
            <li><span className="tick">2</span><div><b>Посмотрите сводку и аналитику</b><span>Выручка, склад, ближайшие сроки отчётности.</span></div></li>
            <li><span className="tick">3</span><div><b>Спросите ассистента</b><span>Он считает по вашим данным, а записи вносит только после вашего подтверждения.</span></div></li>
          </ol>
        </div>
        <p className="small" style={{ opacity: 0.7 }}>Справка по законодательству не заменяет консультацию юриста.</p>
      </div>

      <div className="login-main">
        <form className="login-box" onSubmit={(e) => { e.preventDefault(); login(email) }} noValidate>
          <h1>Вход</h1>
          <p className="muted" style={{ margin: '6px 0 20px' }}>Войдите рабочим email, чтобы открыть данные своей компании.</p>

          {error && <div className="form-err" role="alert">{error}</div>}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className={`input ${error ? 'invalid' : ''}`}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.by"
            />
          </div>
          <button type="submit" className="btn" disabled={loading} style={{ width: '100%', marginTop: 16, height: 38 }}>
            {loading ? 'Входим…' : 'Войти'}
          </button>

          <div className="demo">
            <div className="small muted">Демо-аккаунты, вход в один клик</div>
            {DEMO.map(([address, who]) => (
              <button key={address} type="button" className="demo-acc" disabled={loading} onClick={() => { setEmail(address); login(address) }}>
                <b>{address}</b><span>{who}</span>
              </button>
            ))}
          </div>
        </form>
      </div>
    </div>
  )
}
