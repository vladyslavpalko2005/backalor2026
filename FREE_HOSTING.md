# Безкоштовний запуск: Render Free + Supabase Free

Цей варіант не створює платної Render-бази або постійного диска. API працює на Render Free, а користувачі, сесії, проєкти, права й ZIP-копії зберігаються у PostgreSQL проєкту Supabase Free. Квоти постачальників діють для всього акаунта/проєкту; $0 можливий у межах цих квот.

Поточний локальний `render.yaml` описує саме цей варіант. Платна попередня конфігурація збережена окремо як `render.paid.yaml`.

## Обмеження

- Render Free засинає після 15 хвилин без вхідних запитів. Перше підключення може чекати запуску; якщо клієнт повідомляє недоступність сервера, зачекай і натисни повтор. [Render Free](https://render.com/docs/free).
- Supabase Free наразі включає 500 МБ бази. У цьому варіанті ZIP-копії також займають місце в цій квоті. Один ZIP обмежений **20 МіБ**. Старі копії при успішному оновленні видаляються, але резервні копії корпусу слід зберігати окремо. Це варіант для невеликого дослідницького проєкту. [Квоти](https://supabase.com/pricing).
- Supabase може призупинити Free-проєкт після тижня низької активності; відновлення — у його dashboard. [Умови призупинення](https://supabase.com/docs/guides/platform/free-project-pausing).
- Безкоштовна Render PostgreSQL закінчується через 30 днів, тому для цього варіанта використовується Supabase. [Умови Render](https://render.com/docs/free).
- Не підключай платний план/диск, якщо потрібен бюджет $0. Перевір умови у формах створення ресурсів перед підтвердженням.

## 1. Безкоштовна база Supabase

1. Створи акаунт [Supabase](https://supabase.com/dashboard) і організацію на **Free**.
2. Створи проєкт `backalor`, вибери європейський регіон і надійний пароль бази. Запиши його у своєму менеджері паролів.
3. У **Connect** вибери **Session pooler** та скопіюй PostgreSQL URI з портом **5432**. Цей шлях підтримує IPv4; прямий DB hostname часто потребує IPv6. [Офіційна інструкція](https://supabase.com/docs/guides/database/connecting-to-postgres).
4. Підстав пароль у URI. Спеціальні символи пароля в URL мають бути percent-encoded; не надсилай URI з паролем у чат чи GitHub. Додай `?sslmode=require`, якщо параметр TLS ще відсутній.

Приклад форми, а не робочі облікові дані:

```text
postgresql://postgres.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

Використовуй серверний DB-користувач `postgres.PROJECT_REF`. API сам створить таблиці. Для таблиць PostgreSQL увімкнено RLS без browser-політик: користувачі Supabase Data API не отримують доступу до сесій/даних; наш сервер звертається через привілейоване DB-підключення. Не додавай permissive policies для `anon` або `authenticated`.

## 2. Render Free

Створи **Web Service** з репозиторію, де вже є оновлені файли. Для ручної форми:

| Поле | Значення |
|---|---|
| Language | Docker |
| Branch | main |
| Region | Frankfurt |
| Root Directory | порожнє |
| Instance Type | **Free**, підсумок **$0/month** |
| Health Check Path | `/ready` |
| Persistent Disk | не додавати |

У **Environment** додай:

```dotenv
BACKALOR_DATABASE_URL=URI_З_SESSION_POOLER_SUPABASE
BACKALOR_REQUIRE_POSTGRES=1
BACKALOR_SNAPSHOT_STORAGE=database
BACKALOR_MAX_UPLOAD_BYTES=20971520
BACKALOR_DATA_DIR=/var/data
GOOGLE_CLIENT_ID=ТВІЙ_CLIENT_ID
GOOGLE_CLIENT_SECRET=ТВІЙ_CLIENT_SECRET
```

`/var/data` тут лише тимчасова папка приймання та перевірки ZIP. Після успішного запису в PostgreSQL тимчасовий файл видаляється. Перезапуск Render не видаляє хмарні ZIP. При конфлікті версії або помилці транзакції попередня копія залишається.

Альтернатива ручній формі — **New → Blueprint**, стандартний файл `render.yaml`. Він має `plan: free`, не містить `disk:` і не створює Render Postgres. Запитуваний `BACKALOR_DATABASE_URL` бери з Supabase; OAuth secret додавай лише в Render.

## 3. Google-вхід

Після отримання домену Render додай у Web application OAuth-клієнт точний redirect URI:

```text
https://ТВІЙ-СЕРВІС.onrender.com/auth/google/callback
```

Якщо Google OAuth у Testing, додай свій Google-акаунт до Test users. Перезапусти Render після зміни секретів. `/ready` має повернути `database: postgresql`, а `/health` — `google_configured: true`.

На своєму комп’ютері додай лише:

```dotenv
BACKALOR_API_URL=https://ТВІЙ-СЕРВІС.onrender.com
```

Запусти `launch.command`, увійди через Google та залиш «Запам’ятати вхід», якщо це власний комп’ютер. Локальної серверної БД desktop не створює.

## Google як альтернатива API

[Google Cloud Run](https://cloud.google.com/run/pricing) може запускати той самий Docker-контейнер з цими змінними та Supabase PostgreSQL. Має безкоштовні квоти, проте потрібен billing-акаунт і використання понад квоти оплачується. Google Cloud SQL PostgreSQL не має постійного безкоштовного тарифу; trial не підходить для постійного бюджету $0. [Free program](https://docs.cloud.google.com/free/docs/free-cloud-features).

У Cloud Run додай `BACKALOR_PUBLIC_URL` із HTTPS-адресою сервісу; Render передає свій URL автоматично. Установи мінімум інстансів 0 і врахуй можливу оплату збірки образу, registry та мережевого трафіку. Конфігурація Cloud Run у цьому пакеті автоматично не розгортається.
