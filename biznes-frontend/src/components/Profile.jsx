export default function Profile() {
  return (
    <section>
      <h1>Профиль бизнеса</h1>
      <p className="sub">Чем полнее анкета, тем точнее ответы ИИ</p>
      <div className="card">
        <div className="grid g2">
          <div><div className="k">Название</div><input className="f" defaultValue="Уютный дом" /></div>
          <div><div className="k">УНП</div><input className="f" placeholder="9 цифр" /></div>
          <div><div className="k">Форма</div><select className="f"><option>ИП</option><option>ООО</option></select></div>
          <div><div className="k">Налоговый режим</div><select className="f"><option>УСН</option><option>Общий</option></select></div>
          <div><div className="k">Сотрудников</div><input className="f" defaultValue="6" /></div>
          <div><div className="k">Роль</div><select className="f"><option>Владелец</option><option>Менеджер</option><option>Бухгалтер</option></select></div>
        </div>
        <button className="btn" style={{ marginTop: 14 }}>Сохранить</button>
      </div>
    </section>
  )
}
