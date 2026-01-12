type PlaceholderPageProps = {
  title: string;
  description: string;
};

function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Модуль в разработке</p>
          <h1>{title}</h1>
        </div>
      </header>
      <div className="panel">
        <p>{description}</p>
        <p>Подключим расписания, историю запусков и интеграции в ближайших итерациях.</p>
      </div>
    </div>
  );
}

export default PlaceholderPage;
