// Общие мелочи интерфейса: иконки, заголовок страницы, блок «Следующий шаг».

const paths = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  book: <path d="M4 4h7a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4zM20 4h-5a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h5z" />,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" /></>,
  clip: <path d="M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7" />,
  plus: <path d="M12 5v14M5 12h14" />,
  down: <path d="M12 4v12M6 10l6 6 6-6M4 20h16" />,
  up: <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />,
  ext: <path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" />,
}

export function Icon({ name }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

// Порядок вкладок = порядок работы: увидеть → разобраться → спросить/сделать → проверить по закону.
export const TABS = [
  { id: 'dash', label: 'Обзор', icon: 'home', hint: 'что происходит в бизнесе сейчас' },
  { id: 'an', label: 'Аналитика', icon: 'chart', hint: 'разобраться в цифрах' },
  { id: 'chat', label: 'Ассистент', icon: 'chat', hint: 'спросить и внести изменения' },
  { id: 'kb', label: 'База знаний', icon: 'book', hint: 'проверить по документам' },
  { id: 'prof', label: 'Профиль бизнеса', icon: 'gear', hint: 'данные компании и доступ', settings: true },
]
export const NEXT = { dash: 'an', an: 'chat', chat: 'kb', kb: 'dash', prof: 'dash' }

export function PageHead({ company, tab, title, sub, children }) {
  const t = TABS.find((x) => x.id === tab)
  return (
    <>
      <div className="crumbs">{company} / {t?.label}</div>
      <div className="page-head">
        <div><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
        {children && <div className="actions">{children}</div>}
      </div>
    </>
  )
}

export function NextStep({ tab, go }) {
  const n = TABS.find((x) => x.id === NEXT[tab])
  return (
    <div className="next">
      <div className="muted">Следующий шаг: {n.hint}</div>
      <button className="btn secondary" onClick={() => go(n.id)}>Перейти: {n.label}</button>
    </div>
  )
}
