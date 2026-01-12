FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y gcc libpq-dev ssh-client rsync git iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pytest.ini /app/pytest.ini
COPY pytest_integration.ini /app/pytest_integration.ini
COPY tests /app/tests
COPY tests_integration /app/tests_integration
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
