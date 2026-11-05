# 🤖 AI GitHub PR Review Agent

Автоматический AI-агент для ревью Pull Request-ов в GitHub с отправкой отчётов в Telegram-бота.

## 🚀 Возможности

- **Автоматический запуск:** Срабатывает на открытие или обновление PR в GitHub Actions (`opened`, `synchronize`).
- **Умная фильтрация:** Игнорирует lock-файлы (`package-lock.json`, `poetry.lock` и др.), бинарные файлы, минимизированный код и ассеты, экономя токены и время.
- **Глубокий анализ кода:** Проверяет логику, потенциальные баги, уязвимости безопасности (OWASP), производительность и архитектуру.
- **Построчные комментарии:** Оставляет замечания непосредственно к конкретным строкам кода в GitHub PR.
- **Официальный вердикт:** Выставляет вердикт (`APPROVE`, `REQUEST_CHANGES` или `COMMENT`) с оценкой от 1 до 10.
- **Мгновенные уведомления в Telegram:** Присылает аккуратную карточку с вердиктом, оценкой, резюме и ссылкой на PR прямо в чат команды или личку.
- **Мультипровайдерность:** Поддерживает **Google Gemini** (бесплатный тариф), **DeepSeek**, **Groq**, **OpenAI** или локальные модели через **Ollama**.

---

## 🏗 Архитектура

```
[Разработчик открыл PR]
         │
         ▼
[GitHub Actions Workflow]
         │
         ├──► 1. Скачивает diff и отсекает шумные файлы
         ├──► 2. Отправляет diff в LLM (Gemini / DeepSeek / OpenAI)
         ├──► 3. Публикует Review и комментарии к строкам в GitHub PR
         └──► 4. Отправляет итоговую карточку в Telegram Bot
```

---

## 🛠 Быстрый старт для локального тестирования

1. Клонируйте репозиторий и установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

2. Скопируйте шаблон переменных окружения:
   ```bash
   cp .env.example .env
   ```

3. Заполните `.env`:
   ```dotenv
   GITHUB_TOKEN=ghp_...
   GITHUB_REPOSITORY=owner/repo
   PR_NUMBER=1

   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   TELEGRAM_CHAT_ID=123456789

   LLM_PROVIDER=gemini
   LLM_API_KEY=AIzaSy...
   ```

4. Запустите агент:
   ```bash
   python main.py --repo owner/repo --pr 1
   ```

---

## ⚙️ Настройка в GitHub Actions

### 1. Добавьте секреты репозитория (Repository Secrets)
Перейдите в **Settings → Secrets and variables → Actions → Repository secrets** и добавьте:

| Секрет | Описание |
| :--- | :--- |
| `LLM_API_KEY` | API-ключ выбранного провайдера (например, Gemini из [Google AI Studio](https://aistudio.google.com/)) |
| `TELEGRAM_BOT_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ID чата или группы (можно узнать у [@userinfobot](https://t.me/userinfobot)) |

> ℹ️ **Примечание:** `GITHUB_TOKEN` генерируется GitHub автоматически при каждом запуске воркфлоу, добавлять его вручную не нужно.

### 2. (Опционально) Переменные конфигурации (Repository Variables)
В **Settings → Secrets and variables → Actions → Variables**:

- `LLM_PROVIDER`: `gemini` (по умолчанию), `deepseek`, `groq`, `openai`
- `LLM_MODEL`: Название модели (например, `gemini-2.5-flash`, `deepseek-chat`, `gpt-4o-mini`)
- `MAX_DIFF_LINES`: Лимит строк diff (по умолчанию `1500`)

### 3. Разрешения для GitHub Actions
Перейдите в **Settings → Actions → General → Workflow permissions** и убедитесь, что выбрано:
- **Read and write permissions** (необходимо, чтобы агент мог оставлять комментарии и ревью в PR).

---

## 📲 Пример сообщения в Telegram

```text
🤖 AI Code Review | owner/repo
PR: #42 Add OAuth2 Authentication
👤 Автор: @developer
📊 Вердикт: ⚠️ Требуются правки (Changes Requested)
📈 Оценка качества: ⭐️⭐️⭐️ (6/10)

📝 Резюме:
Добавлена аутентификация через OAuth2. Реализация в целом хорошая, 
но обнаружена уязвимость отсутствия проверки state-параметра (CSRF) 
и потенциальная утечка токена в логах.

🔍 Ключевые моменты:
• ✅ Чистая структура роутов и middleware
• ⚠️ Отсутствует CSRF-токен в callback-обработчике
• ⚠️ Токен доступа логируется на уровне INFO

💬 Замечаний в коде: 2
  └ src/auth/oauth.py:48: Отсутствует валидация параметра state (CSRF уязвимость).
  └ src/auth/oauth.py:72: Чувствительный access_token выводится в логи.

🔗 Открыть Pull Request на GitHub
```

---

## 🧪 Запуск тестов

```bash
python3 -m unittest discover tests
```

---

## 📄 Лицензия

MIT
