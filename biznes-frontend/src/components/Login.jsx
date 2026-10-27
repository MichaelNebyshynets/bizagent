import { useState } from 'react'

export function Login({ onLogin }) {
  const [email, setEmail] = useState('owner@uyut.by')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Пользователь не найден или ошибка сервера')
      }

      localStorage.setItem('auth_token', data.access_token)
      localStorage.setItem('user_name', data.name)
      localStorage.setItem('user_role', data.role)
      
      onLogin(data)
    } catch (err) {
      console.error('Login error:', err)
      setError(err.message || 'Ошибка подключения к бэкенду')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#14161b', color: '#e2e8f0' }}>
      <div className="card" style={{ width: '100%', maxWidth: '420px', padding: '32px', background: '#1f2228', border: '1px solid #30353e', borderRadius: '12px' }}>
        <h2 style={{ marginBottom: '8px', fontSize: '20px', color: '#fff' }}>Вход в Бизнес<b>Помощник</b></h2>
        <p className="sub" style={{ marginBottom: '24px' }}>Введите ваш email для авторизации</p>

        {error && (
          <div style={{ color: '#ff4d4d', background: 'rgba(255,77,77,0.1)', padding: '10px 12px', borderRadius: '6px', marginBottom: '16px', fontSize: '13px', border: '1px solid rgba(255,77,77,0.3)' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <div className="k" style={{ marginBottom: '6px', fontSize: '13px', color: '#8f96a3' }}>Email пользователя</div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="owner@uyut.by"
              required
              className="f"
              style={{ width: '100%', padding: '10px 12px', background: '#14161b', border: '1px solid #30353e', borderRadius: '6px', color: '#fff' }}
            />
          </div>

          <button type="submit" disabled={loading} className="btn" style={{ width: '100%', padding: '12px', cursor: 'pointer', fontWeight: 'bold' }}>
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>

        <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid #30353e', fontSize: '12px', color: '#8f96a3' }} className="src">
          <p style={{ marginBottom: '8px' }}><strong>Тестовые аккаунты:</strong></p>
          <ul style={{ paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <li><code>owner@uyut.by</code> — Владелец (Уютный дом)</li>
            <li><code>manager@uyut.by</code> — Менеджер (Уютный дом)</li>
            <li><code>accountant@uyut.by</code> — Бухгалтер (Уютный дом)</li>
            <li><code>owner@flora.by</code> — Владелец (Флора)</li>
          </ul>
        </div>
      </div>
    </div>
  )
}