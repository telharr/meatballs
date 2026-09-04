# Приваты: карта как в игре (World Map)

Панель **не пишет `saves/`**. Зоны создаёт JVM через `SafeHouse.addSafeHouse` (мод `MeatballsSafehouses`). Карта в браузере — только указатель координат и оверлей.

## Что есть сейчас (Sprint 13 Phase A)

На вкладке **Приваты** бумажный атлас Knox из тех же векторов, что ISWorldMap (клавиша M): `worldmap.xml` + `worldmap-forest.xml` из каталога клиента. PNG лежит в `panel/data/maps/knox/atlas.png` (gitignore). Нет атласа — схема с AABB городов.

Собрать атлас на машине с установленной игрой:

```text
python tools/knox_atlas.py
python tools/knox_atlas.py --game-dir "C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
```

`PZ_GAME_DIR` тоже подходит. Текстуры Indie Stone не копируются и не коммитятся.

## Что игрок называет «картой админки»

В ванильной **ISAdminPanelUI** карты нет. Админский Add Safezone (`ISAddSafeZoneUI`) — два угла в 3D-мире, не карта.

Карта, которую админы открывают в игре — **ISWorldMap** (клавиша M / кнопка карты): бумажный атлас Knox Country, у staff без тумана (`SeeWorldMap`). Цель панели — **тот же атлас + наши прямоугольники**, а не спутник OSM.

## Система координат (контракт, не ломать)

| Вещь | Значение |
|------|----------|
| API | `SafeHouse.addSafeHouse(x, y, w, h, owner)` |
| Оси | X вправо, **Y вниз** (север = меньший Y) |
| Cell | **300×300** тайлов (`worldmap.xml` точки 0–300). Сетка панели = ячейка мира. |
| Калибровка | `panel/data/maps/knox/calibration.json` + AABB из `panel/safehouses.py` `CITIES` |

Любой растр/тайл **обязан** давать `pixel → worldXY` с ошибкой меньше ~2 тайлов на зуме размещения (8×8 зона).

## Варианты (честно)

| ID | Подход | Плюс | Минус | Вердикт |
|----|--------|------|-------|---------|
| A | PNG из `worldmap.xml` + affine (x0,y0,x1,y1) на canvas | Офлайн, тот же Draw, без копирайтных текстур TIS | На сильном зуме мыло | **Сделано (3.24.0)** |
| B | Пирамида тайлов (Leaflet), нарезка атласа | Зум до дома | Гигабайты, пайплайн | next, если A мало |
| C | iframe map.projectzomboid.com / чужой GIS | «Бесплатно красиво» | Нет drag-зоны, CORS | **Не делать** |
| D | Парсить XML/текстуры в рантайме панели | Как M без предсборки | Хрупко, нужен путь к игре у панели | A уже берёт XML на этапе сборки |

## Право и репозиторий

Текстуры World Map — ассеты The Indie Stone. **Не коммитить** оригинальные PNG и сгенерированный `atlas.png`.

- Класть атлас в `panel/data/maps/knox/` (gitignore `*.png`).
- В репо: `calibration.json`, `tools/knox_atlas.py`, загрузчик.
- Fallback: схема, если PNG нет.

## Как это вставлено

1. `GET /api/safehouses` → `map.atlas.url` (`/api/safehouses/map/atlas?v=mtime`).
2. `privates-map.js` рисует `drawImage` под сеткой/зонами. Draw по-прежнему пишет X/Y/W/H.
3. Проверка: зона `MB-panel-probe` 10648,6912 должна лежать на западном крае West Point, как в игре.

Later: `tools/knox_tiles.py` + Leaflet, если зума A мало. **Не трогать** сейвы, F8, чужие GIS.

## События моста (dedicated)

Headless dedicated **часто не вызывает `Events.OnTick`**. Поллер cmd: `OnServerStarted` (сразу) + `EveryOneMinute` / `EveryTenMinutes` + OnTick если вдруг есть (listen server). Файл `Lua/mb_safehouse_cmd.txt` — CRLF с FTP допустим, парсер снимает `\r`.
