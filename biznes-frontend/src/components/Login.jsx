import { useEffect, useState } from 'react'

const DEMO = [
  ['owner@uyut.by', 'Владелец, Уютный дом'],
  ['manager@uyut.by', 'Менеджер, Уютный дом'],
  ['accountant@uyut.by', 'Бухгалтер, Уютный дом'],
  ['owner@flora.by', 'Владелец, Флора'],
]

export function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [demoMode, setDemoMode] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/health', { signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (!controller.signal.aborted) setDemoMode(data?.db === 'mock') })
      .catch(() => {})
    return () => controller.abort()
  }, [])

  const login = async (value, demo = false) => {
    const address = value.trim()
    if (!/^\S+@\S+\.\S+$/.test(address)) {
      setError('Введите email в формате name@company.by')
      return
    }
    if (!demo && !password) {
      setError('Введите пароль')
      return
    }
    setError('')
    setLoading(true)
    try {
      const response = await fetch(`/auth/${demo ? 'demo' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(demo ? { email: address } : { email: address, password }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось войти')
      }
      localStorage.setItem('auth_token', data.access_token)
      localStorage.setItem('user_name', data.name)
      localStorage.setItem('user_role', data.role)
      localStorage.setItem('user_company', data.company || '')
      localStorage.setItem('user_email', address.toLowerCase())
      setPassword('')
      onLogin(data)
    } catch (err) {
      console.error('Login error:', err)
      setError(err.message === 'Failed to fetch'
        ? 'Сервер не отвечает. Откройте окно БизнесПомощника и проверьте сообщение о запуске.'
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
          <p className="muted" style={{ margin: '6px 0 20px' }}>Введите email и пароль, чтобы открыть данные своей компании.</p>

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
          <div className="field">
            <label htmlFor="password">Пароль</label>
            <input id="password" className="input" type="password" autoComplete="current-password"
              value={password} maxLength={128} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button type="submit" className="btn" disabled={loading} style={{ width: '100%', marginTop: 16, height: 38 }}>
            {loading ? 'Входим…' : 'Войти'}
          </button>

          {demoMode && <div className="demo">
            <div className="small muted">Демо-аккаунты, вход в один клик</div>
            {DEMO.map(([address, who]) => (
              <button key={address} type="button" className="demo-acc" disabled={loading} onClick={() => { setEmail(address); login(address, true) }}>
                <b>{address}</b><span>{who}</span>
              </button>
            ))}
          </div>}
        </form>
      </div>
    </div>
  )
}
