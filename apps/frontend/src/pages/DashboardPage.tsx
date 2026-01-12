const cards = [
  { title: "Хосты", value: "0", hint: "В ожидании добавления" },
  { title: "Автоматизация", value: "0", hint: "Последний запуск не отрабатывал" },
  { title: "Секреты", value: "0", hint: "Всё защищено" },
];

function DashboardPage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Обзор инфраструктуры</p>
          <h1>Дашборд IT Manager</h1>
        </div>
      </header>
      <div className="grid cards">
        {cards.map((card) => (
          <div key={card.title} className="metric-card">
            <p className="metric-title">{card.title}</p>
            <p className="metric-value">{card.value}</p>
            <p className="metric-hint">{card.hint}</p>
          </div>
        ))}
      </div>
      <div className="panel small">
        <h2>Статус системы</h2>
        <p>Backend ждёт миграций и интеграции Ansible Runner. Frontend готов к подключениям.</p>
      </div>
    </div>
  );
}

export default DashboardPage;
