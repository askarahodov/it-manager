import os
import sys
from pathlib import Path


# Настраиваем окружение до импорта app.* модулей (conftest импортируется на старте pytest).
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("MASTER_KEY", "test-master-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Гарантируем, что `import app` работает независимо от текущей директории запуска pytest.
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
