# MEATBALLS Control — меморандум целей

**Обязательно прочитать в начале сессии** вместе с `docs/SESSION.md`, прежде чем менять панель, FTP, хост или моды.

`SESSION.md` — факты текущего мира (IP, моды, флаги). Этот файл — **зачем продукт** и **какие правила не ломаем**. Спринты: `docs/SPRINTS.md`.

---

## 1. Зачем это есть

Сделать **свою панель управления dedicated-серверами Project Zomboid**, не привязанную к одному игровому хостингу (XLGAMES, G-Portal, Nitrado, свой VPS, локальный дедик).

Админ подключает **профиль сервера** (координаты доступа), а панель даёт одни и те же операции: консоль, игроки, логи, моды, файлы, рестарт.

Первый живой инстанс — MEATBALLS на XLGAMES. Он **референс**, не единственный допустимый бэкенд.

---

## 2. Что уже записано, а что нет

| Документ | Роль |
|----------|------|
| `docs/PRODUCT.md` (этот файл) | Цели, границы, профиль сервера, честность по стандартам |
| `docs/SPRINTS.md` | Очередь реализации |
| `docs/SESSION.md` | Живые факты хоста / панели / модов (без паролей) |
| `docs/architecture.md` | Lua / клиент-сервер PZ |
| `docs/setup.md` | Машина разработчика |
| `panel/README.md` | Как поднять текущую панель |

Раньше шаги жили в чате и в `SESSION.md`. Этого мало для продукта: нет контракта «что такое сервер» и нет спринтов. С этого файла контракт есть.

---

## 3. Соответствие стандартам (честно)

### Современная веб-панель (Pterodactyl, AMP, Cosmic)

| Ожидание | У нас сейчас | Вердикт |
|----------|--------------|---------|
| Несколько серверов / профилей | Профили 3.8.0, `.env` = миграция | Да |
| Логин оператора, роли | Открытый `127.0.0.1:8000` | Нет |
| Аудит действий | Нет журнала «кто нажал quit» | Нет |
| Секреты вне git | `.env` gitignore | Да |
| Health / статус | RCON, Query, FTP, мир | Частично |
| Мастер «подключить сервер» | Главная 3.9.0 + capabilities, серые вкладки | Да |
| HTTPS, CSRF, сессии | Локальная панель без auth | Не для публичного интернета |
| Тесты API / UI | Почти нет | Нет |
| Версионирование API | FastAPI `3.9.0` | Частично |

Стек (FastAPI + статическая SPA) для **операторской** панели нормальный. Это не отставание. Отставание — **один тенант, нет auth, нет профиля**.

### Панели PZ-хостингов (XLGAMES и аналоги)

Они почти всегда умеют: старт/стоп JVM, файловый менеджер, INI, консоль, иногда логи. Они **не** умеют PZ-специфику: LogExtender, чат из `_chat.txt`, приваты, каталог модов репо, точечный вайп с бэкапом.

Мы уже сильнее хостера в предметной области и слабее в «кнопка Start процесса» и в «добавь второй сервер».

**Правило:** не притворяться, что панель запускает JVM на чужом хостинге, если хостер не дал API. Честно писать: `save` / `quit` / «хостер поднимет процесс».

---

## 4. Принципы (не ломать)

1. **Хостинг — адаптер, не ядро.** Ядро говорит: RCON, файлы, процесс (если есть). XLGAMES — один адаптер.
2. **Секреты не в git и не в `SESSION.md`.** Профили хранить в `panel/data/servers/` (gitignore) или encrypted store.
3. **Saves / WorldDictionary** — только с явным confirm (вайп чанка уже так).
4. **Игроки ≠ NPC.** Тренеры не в Steam, не в RCON `players`, не в шапке.
5. **XLGAMES важнее** остаётся политикой *конкретного* профиля, не глобальной религией.
6. **Панель читает мир, моды меняют мир.** Тикеты, дамп приватов — мод или лог, не фантазия RCON.
7. **Сначала контракт профиля и проба связи, потом новые вкладки.**

---

## 5. Алгоритм: админ подключает сервер

Независимо от хостинга админ должен знать **три канала**. Без них панель деградирует, а не падает целиком.

```text
1. Идентичность     имя, заметка, версия PZ (B42.x)
2. Игроки видят     публичный IP/DNS + UDP game + UDP query
3. Админ командует  RCON TCP + пароль
4. Админ правит     FTP / FTPS / SFTP / локальный путь к cachedir
5. Кто поднимает JVM  none | host-panel | local-process | custom-API
```

### Обязательный минимум (профиль валиден)

| Поле | Зачем | Откуда админ берёт |
|------|--------|-------------------|
| `name` | Подпись в UI | Сам придумывает |
| `rcon.host` | Команды: players, save, kick, quit | Панель хостера / `server.ini` `RCONPort` |
| `rcon.port` | Обычно не game-порт | Хостер: «RCON» |
| `rcon.password` | Auth Source RCON | Хостер → Settings / `RCONPassword=` |
| `files.kind` | `ftp` \| `sftp` \| `local` | Чем хостер отдаёт диск |
| `files.root` | Cachedir на диске | Часто `/ServerWorld` или `Zomboid` |
| `files.ini` | Имя INI | `world.ini` / `servertest.ini` / кастом |

Без RCON нет живого управления. Без файлов нет логов, INI, модов, банов, чата, вайпа.

### Нужно для полной панели (как у MEATBALLS)

| Поле | Канал | Если нет |
|------|--------|----------|
| `ftp.host` `port` `user` `password` | Файлы | Только RCON-консоль |
| `ftp.tls` / SFTP | Безопасность | Риск plaintext FTP |
| `paths.logs` | Обычно `{root}/Logs` | Вкладка Логи/Чат пустая |
| `paths.db` | `{root}/db` | Баны пустые |
| `paths.lua` | `{root}/Lua` | Слоты / дамп приватов |
| `paths.mods` | `{root}/mods` или `/mods` | Заливка модов вручную |
| `public.host` `game_port` `query_port` | Инвайт + A2S | Инвайт врёт |
| `public.max_players` | Шапка | Дефолт 32 |
| `process.kind` | Старт JVM | Кнопка Start скрыта или «открой панель хостера» |

### Не секреты, но полезно

- `game_version` (42.20.4) — не слать B41-моды
- `hoster` (`xlgames` \| `gportal` \| `nitrado` \| `vps` \| `local`) — подсказки путей
- `authority` (`host_wins` \| `panel_wins`) — кто главный в INI
- Discord webhook / invite — опционально

### Проба после сохранения профиля (мастер)

1. TCP RCON + команда `players`
2. UDP Query (A2S), если указан query-порт
3. LIST/STAT файлового корня, найти `server-console.txt` и INI
4. Записать `capabilities`: `{ rcon, files, query, process }`
5. Вкладки без capability — disabled с текстом «нужен FTP», не 500

---

## 6. Где мы сейчас (Deployment & packaging)

Панель **3.17.0** — Sprint 6 distribution:

- `docs/DEPLOYMENT.md` — Local desktop, Linux VPS (systemd + Nginx WS), Docker Compose
- `packaging/build_exe.py` + `installer.iss` — PyInstaller bundle + Inno Setup wizard
- `Dockerfile` / `docker-compose.yml` — volumes `/data`, `/mirror`

Панель **3.16.0** — WebSocket event bus + telemetry + RBAC:

- `WS /ws/events` — live `status`, `telemetry`, `workshop_progress`, `console_tail`
- RBAC: `admin` vs `moderator`

Панель **3.15.0** — SteamCMD bootstrap + ModPack FTP deploy

Панель **3.14.0** — in-game AdminTools ↔ panel:

- `GET /api/admintools/cities`, `POST /api/admintools/city-wipe` (file drop + RCON notify)
- `GET /api/admintools/audit` — structured admin/cmd journal
- Hard FS chunk wipe remains under advanced toggle on Зеркало

Ранее: **3.13.x** Snapshot / Workshop; **3.12** SFTP; **3.11** JWT + i18n.

---

## 7. Как вести работу

- Новый чат: `PRODUCT.md` → `SESSION.md` → код.
- Смена цели или спринта — правка этих двух файлов плюс `SPRINTS.md`.
- Не коммитить `.env`, `panel/data/servers/*`, `panel/backups/*`.
- Не обещать Start на хостинге без их API.
