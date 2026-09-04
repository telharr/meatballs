# Спринты — MEATBALLS Control

Читать после `docs/PRODUCT.md`. Статусы: `done` / `now` / `next` / `later`.

**Текущий фокус:** Sprint 13 Phase A **done** (атлас ISWorldMap, панель 3.24.0). Дальше тайлы (Phase B), если зума PNG мало.

---

## Уже сделано (не спринт, базис)

Однохостовая панель 3.7.0 на FastAPI + SPA:

- Главная, RCON-консоль, игроки, NPC, файлы, моды, планировщик
- Логи (типы), чат из `_chat.txt`, баны из `db/`, приваты из дампа
- Зеркало FTP, локальный дедик, точечный вайп с confirm
- Политика «хостер важнее» для watched INI

Дыры базиса: нет списка серверов, нет логина, LogExtender-дамп не залит на живой хост.

---

## Sprint 0 — устав (done)

- [x] Меморандум `docs/PRODUCT.md`
- [x] Этот файл спринтов
- [x] Обязательное чтение в `AGENTS.md`, `docs/SESSION.md`, `.cursor/rules`

---

## Sprint 1 — профили серверов (done)

**Цель:** админ добавляет второй сервер теми полями, что в меморандуме, и переключает панель без правки `.env` руками каждый раз.

**Контракт** `panel/data/servers/<id>.json` (gitignore) + индекс `panel/data/servers.json`:

```json
{
  "id": "meatballs-xl",
  "name": "MEATBALLS",
  "hoster": "xlgames",
  "game_version": "42.20.4",
  "rcon": { "host": "", "port": 16284, "timeout": 10 },
  "files": {
    "kind": "ftp",
    "host": "",
    "port": 21,
    "user": "",
    "tls": false,
    "root": "/ServerWorld",
    "mods": "/ServerWorld/mods",
    "ini": "world.ini"
  },
  "public": { "host": "", "game_port": 16282, "query_port": 16281, "max_players": 32, "name": "MEATBALLS PZ" },
  "process": { "kind": "none" },
  "authority": "host_wins"
}
```

Пароли — отдельный `panel/data/secrets/<id>.json` или поля только в gitignore-файле, не в репозитории.

**Алгоритм UI «Добавить сервер»**

1. Имя + хостер (подставляет дефолтные порты/пути).
2. RCON host/port/password → кнопка «Проверить» (`players`).
3. Файлы: kind + host/user/pass + root → «Проверить» (LIST, найти console + ini).
4. Публичный IP/порты → опционально Query.
5. Процесс: none / local / (позже API).
6. Сохранить, сделать активным, перечитать health/mirror roots как `{id}`.

**Код**

- `panel/servers.py` — CRUD, active id в prefs
- Все `client_from_env()` / `RconConfig.from_env()` читают **активный профиль**, `.env` = профиль по умолчанию при первом старте (миграция)
- Шапка: переключатель сервера
- Зеркало: `.mirror/<id>/` чтобы два мира не смешивались

**Приёмка**

- [x] Текущий XLGAMES работает как профиль после миграции из `.env`
- [x] Можно добавить local dedi вторым профилем (`files.kind=local`, `process.kind=local`)
- [x] Секреты не попадают в git и в `SESSION.md`

---

## Sprint 2 — мастер и capabilities (done)

**Цель:** вкладки не врут, если канала нет.

- [x] Мастер на Главной: «Подключить сервер»
- [x] После пробы записать `capabilities: {rcon, files, query, process}`
- [x] Disabled + подсказка: Чат/Логи без files, Start без process
- [x] Пресеты хостеров: XLGAMES (`/ServerWorld`, world.ini), vanilla VPS (`Zomboid`, servertest.ini)

**Приёмка:** профиль только с RCON открывает Консоль и Игроки, Логи серые.

---

## v1 onboarding — universal panel (done, panel 3.10.0)

**Цель:** zero-config path для любого PZ-хоста: wizard → mirror → smoke.

- [x] `GET /api/onboarding`, модал первого запуска
- [x] Черновик профиля (`draft: true`), Edit/Delete активного профиля
- [x] Deep file probe: `server-console.txt`, `*.ini`, `Logs/`
- [x] Предупреждение при `files.kind=local`
- [x] Вкладка **Smoke test** + `panel/services/local_runner.py`
- [x] `docs/ONBOARDING.md`, обновлены `PRODUCT.md` §6 и `panel/README.md`

**Приёмка:** без `.env` и профилей → wizard → Pull → Smoke Start/Stop → переключение профиля.

**Отложено:** JWT (Sprint 3), i18n, SFTP, MEATBALLS plugin toggle.

---

## Sprint 3 — операторы (done, panel 3.11.0)

**Цель:** панель нельзя оставить голой в интернете + RU/EN UI.

- [x] JWT + HttpOnly cookie, `panel/auth.py`, `panel/routes/auth.py`
- [x] Admin из `.env` (`ADMIN_USER` / `ADMIN_PASS_HASH`) или `panel/data/auth.json`
- [x] First-run setup modal, login/logout, user badge
- [x] Middleware: все `/api/*` кроме health + auth login/status/setup
- [x] WebSocket `/ws/console` — token query или cookie
- [x] `AUTH_DISABLED=true` для local dev
- [x] i18n: `panel/static/locales/{ru,en}.json`, switcher RU|EN, localStorage

**Приёмка:** без токена API 401; WS без token закрывается; язык переключается на всех вкладках.

---

## Sprint 4 — SFTP + MEATBALLS plugins (done, panel 3.12.0)

**Цель:** Linux VPS через SFTP; MEATBALLS-фичи включаются per-profile.

- [x] `panel/services/sftp_client.py` + `paramiko` — list/read/write/pull_tree (mirror)
- [x] `files.kind=sftp`, port 22, `sftp_key_path`, пароль/inline key в secrets
- [x] Deep probe: `server-console.txt`, `*.ini`, `Logs/`
- [x] `active_files_client()` — FTP + SFTP через один интерфейс
- [x] `plugins.meatballs` — NPC, Приваты, каталог модов скрыты когда `false`
- [x] Wizard: SFTP (SSH) в dropdown, toggle MEATBALLS, i18n RU/EN

**Приёмка:** профиль `kind=sftp` → probe → mirror Pull → логи; generic VPS без MEATBALLS — чистая universal UI.

---

## Sprint 5 — Workshop / ModPack / update monitor (done, panel 3.13.0)

**Цель:** скачать WorkshopItems в зеркало для Smoke, собрать unified ModPack, видеть обновления Steam.

- [x] `tools/workshop_downloader.py` + `panel/services/workshop_downloader.py` — SteamCMD batch → `.mirror/<id>/steamapps/...` + link в `mods/`
- [x] `tools/pack_merger.py` — tiledef / texture / Lua hook conflicts + `compile_unified_pack`
- [x] `panel/services/workshop_monitor.py` — Steam `GetPublishedFileDetails`, badge UPDATE, optional RCON graceful restart
- [x] API `panel/routes/workshop.py` + вкладка **Workshop**
- [x] i18n RU/EN, docs ONBOARDING / PRODUCT

**Приёмка:** Check Updates → metadata; Download Missing (SteamCMD auto-bootstrap); Compile pack → conflict log; one-click FTP deploy — **3.15.0**.

---

## Sprint 6 — Zero-Touch Deployment & Packaging (done, panel 3.18.0)

**Цель:** end-user дистрибуция — документация сценариев A/B/C + Windows installer pipeline.

- [x] `docs/DEPLOYMENT.md` — Local desktop, Linux VPS (systemd + Nginx WS), Docker
- [x] `docs/ONBOARDING.md` — zero-config first boot, SteamCMD auto-download, wizard detection
- [x] `packaging/build_exe.py` — PyInstaller onedir → `dist/PZControlPanel/`
- [x] `packaging/installer.iss` — Inno Setup: Local vs Remote wizard, `.env` generation, desktop shortcut
- [x] `Dockerfile` + `docker-compose.yml` — volumes `/data`, `/mirror`
- [x] `.gitignore` — `dist/`, `build/`, `Output/`, `*.exe`

**Приёмка:** `python packaging/build_exe.py` → runnable bundle; installer writes `.env`; `docker compose up` → health OK; DEPLOYMENT nginx WS config documented.

**Не в scope:** code signing, auto-update channel, macOS .dmg.

---

## Sprint 10 — единый мастер «Добавить сервер» (now → implementing, panel 3.21.0)

**Цель:** одна явная точка входа «Добавить сервер»; оба режима (VPS/SSH и хостинг вручную) живут в одном продуктовом мастере, а не в двух местах UI.

**Контекст:** раньше сайдбар «+ Добавить сервер» открывал только Amnezia/VPS, а длинная форма на Главной («Подключить сервер») дублировала создание профиля. Пользователь не понимал, куда идти.

**UX-контракт**

```text
[+ у переключателя серверов]  →  шаг 0 «Как подключаем?»
                                      ├─ VPS / Linux     → существующий VPS-модал (SFTP | Auto-Deploy)
                                      ├─ Хостинг вручную → шаги B1–B5 (имя → RCON → файлы → порты → JVM)
                                      └─ Локальный дедик → короткий B с preset local
ПКМ / «Изменить профиль»     →  тот же shell, без шага 0 (edit)
Главная                      →  карточка «Подключение» активного профиля (не второй create)
0 серверов                   →  empty state с тем же CTA
```

**Код / UI**

- [x] Модал `#add-server-wizard`: path picker + stepped `#server-form`
- [x] CTA: `+` рядом с `#server-dd`; убрать nav-item «+ Добавить сервер» из списка вкладок
- [x] Bottom-nav / onboarding / empty state → `openAddServerWizard()`
- [x] Главная: карточка подключения + Edit/Delete; форма create только в мастере
- [x] Edit профиля открывает мастер на шаге B1 (все шаги доступны Назад/Далее)
- [x] i18n RU/EN для шага 0 и кнопок мастера
- [x] `docs/ONBOARDING.md` / `PRODUCT.md` §5–6: один вход, две ветки
- [x] Static cache-bust `?v=3.21.0`

**Приёмка**

- [x] Один понятный «Добавить сервер» (сайдбар `+` или empty state)
- [x] Шаг 0 предлагает VPS / хостинг / local; VPS и ручной путь оба работают
- [x] На Главной нет второго мастера создания; Edit открывает тот же wizard
- [ ] После Save+Activate — профиль в списке, оверлей переключения как сейчас *(ручная проверка в UI)*

**Не в scope:** новый backend API; code signing; объединение Auto-Deploy и игрового профиля в один POST.

---

## Sprint 11 — обновления панели (GitHub Releases) (now, panel 3.22.0)

**Цель:** уведомлять о новых релизах и обновлять панель **без затирания** профилей, secrets и `.env`.

**Контракт state**

```text
App (заменяемо)     panel/*.py, static/, tools/, exe
State (persist)     PANEL_DATA_DIR | %LOCALAPPDATA%/PZControlPanel/data | panel/data (dev/docker)
                    backups/, updates/ рядом
.env                onlyifdoesntexist в Inno; не в GitHub zip
```

**Код / UI**

- [x] `panel/paths.py` — `DATA_DIR` / миграция с legacy `panel/data` для frozen
- [x] Все writers читают `DATA_DIR` (servers, auth, prefs, scheduler, …)
- [x] `GET /api/panel/updates` — GitHub `releases/latest` (`PANEL_UPDATE_REPO`)
- [x] Banner + «Обновить» / «Позже» (snooze в prefs)
- [x] Windows frozen: download setup → SHA256 (если есть) → backup zip → launch Inno
- [x] Inno: `.env` `onlyifdoesntexist`; version sync with `panel/version.py`
- [x] Docker/git: подсказка в API (не silent destroy volumes)
- [x] `panel/version.py` = semver релиза

**Приёмка**

- [ ] После обновления installer профили на месте; `.env` не перезаписан
- [ ] Banner при `latest > current`; snooze скрывает до следующего тега *(проверка на VPS 3.22.0 → 3.22.1)*
- [ ] Docker: `compose pull && up -d` без `-v` сохраняет `/data`

**Не в scope:** silent auto-update без клика; code signing; macOS.

---

## Sprint 12 — приваты: карта, создание, снятие, правка (now, panel 3.23.0)

**Цель:** вкладка **Приваты** повторяет админский Add Safezone / Safehouse UI: карта Knox Country, подсветка зон, прямоугольник, владелец/члены, снятие. Работает на **любом** профиле с каналом файлов, не только XLGAMES.

**Почему мод:** `SafeHouse.*` живёт в JVM дедика. Панель сейв не пишет, RCON слэш-команд персонажа не эмулирует. Хостинг-агностичный мост — файл в `Lua/` + серверный Lua, как city wipe.

**Контракт**

```text
Браузер (карта + форма) → POST /api/safehouses/{create|update|release|install}
Панель → Lua/mb_safehouse_cmd.txt (FTP/SFTP/local cachedir)
Мод MeatballsSafehouses (~1 с) читает, чистит, вызывает SafeHouse.*
Сразу пишет mb_safehouses.json + mb_safehouse_ack.json + mb_safehouse_bridge.json
Панель Pull / poll ack → оверлей
```

Формат команды (без JSON-парсера в Lua):

```text
op=create|update|release
nonce=...
x= y= w= h=
owner=...   title=...   members=a,b   add=...   kick=...
---
```

Строки `owner` / `title` / члены — percent-encoding. Ключ зоны: `x,y,w,h` (title может смениться).

**Мод** `src/mods/MeatballsSafehouses` (B42, без ServerTweaker/LogExtender/AdminTools):

- [x] Дамп `mb_safehouses.json` (совместим с LogExtender)
- [x] Поллер `mb_safehouse_cmd.txt` + ack/bridge
- [x] create / update (title, owner, add/kick) / release
- [x] рассылка `sendServerCommand` онлайн-клиентам
- [x] в каталоге; кнопка «Залить мод» по `files.root/mods/`

**Панель**

- [x] Приваты видны при `capabilities.files` (не только `plugins.meatballs`)
- [x] Карта Knox: pan/zoom, города, оверлей зон, drag-прямоугольник
- [x] Форма как ISAddSafeZoneUI: title, owner, members, размер, пересечение
- [x] Карточка зоны: правка / снятие (confirm `release`)
- [x] Refresh тянет дамп с FTP; без мода — честный empty state
- [x] POST admin + step-up; сейвы не трогаем
- [x] i18n RU/EN, cache-bust `3.23.2` (Приваты: статус «ждём рестарт JVM», не «мод не залит»)

**Приёмка**

- [x] `python tests/test_safehouses.py` — encode/overlap roundtrip
- [x] UI: карта Knox, города, Draw/Pan, форма title/owner/XYWH, size tiles
- [x] Вкладка на профиле с FTP (не только meatballs plugin)
- [x] Залить мод на активный сервер → файлы в `mods/MeatballsSafehouses` *(Приваты → Залить мод **или** Workshop → только этот мод → «Залить выбранные как есть»)*
- [x] Команда create пишется в `Lua/mb_safehouse_cmd.txt` (проверено локально и FTP)
- [x] После рестарта дедика: мост `1.0.0` в консоли; **OnTick на headless не поллит cmd** (исправление 1.1.0: poll на `OnServerStarted` + `EveryOneMinute`)
- [x] Create → ack → дамп: зона `MB-panel-probe` 10648,6912 8×8 (2026-09-04, мод 1.1.1)

**Не в scope Sprint 12:** правка границ без release+create; фракции; продление `lastVisited`; in-game заливка пола с панели.

Карта «как в игре»: `docs/privates-map.md`, **Sprint 13**.

---

## Sprint 13 — карта приватов как ISWorldMap (done / next tiles)

**Цель:** на вкладке Приваты тот же бумажный атлас Knox, что админ видит по M, с оверлеем зон и Draw → `SafeHouse` X/Y.

**Не цель:** спутник OSM, iframe чужого сайта, коммит копирайтных PNG в git.

**Порядок**

1. [x] Калибровка `panel/data/maps/knox/calibration.json` + атлас вне git (`python tools/knox_atlas.py` из `worldmap.xml`).
2. [x] `privates-map.js`: `drawImage` атласа, схема — fallback. Панель **3.24.0**.
3. [ ] Приёмка в браузере: клик по West Point / Muldraugh совпадает с игрой ±2 тайла; `MB-panel-probe` 10648,6912 на карте.
4. Later: тайловая пирамида, если зума A мало.

Детали: `docs/privates-map.md`.

---

---

## Sprint 7 — процесс JVM (later)

**Цель:** Start/Stop там, где это реально.

| kind | Поведение |
|------|-----------|
| `none` | Текст «открой панель хостера» |
| `local` | Уже есть `tools/local_server.py` |
| `http` | Опциональный webhook хостера (если появится API) |

Не эмулировать Start на XLGAMES.

---

## Sprint 8 — тикеты (later, отдельная игровая система)

Панель только **отображает и закрывает**. Источник — мод (команда / запись в `Lua/mb_tickets.json` или лог).

Не начинать, пока нет ТЗ по игровому UX (кто пишет, кто видит, антиспам).

---

## Sprint 9 — качество веб-панели (сквозной)

Параллельно с 1–2, не вместо:

- Пробы API без живого хоста (мок RCON/FTP)
- Кеш-баст уже есть (`?v=`); не забыть при релизах
- Не тащить тяжёлый фронт-фреймворк, пока нет мультипользовательского SPA-ада

---

## Не делать в спринтах 1–2

- Фейковый онлайн / NPC в Steam
- LastDay в `WorkshopItems=`
- Полный вайп `Saves/`
- «Универсальный Start» для всех хостеров
- Публикация панели в интернет без Sprint 3
