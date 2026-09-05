# Agent session log

**Сначала** `docs/PRODUCT.md` (цели панели, профиль сервера), **потом** этот файл. Спринты: `docs/SPRINTS.md`.

Last updated: 2026-09-05 (4/5 on Steam; Gameplay next; branch `mod`)

## Host (do not commit secrets)

Fill this section **locally only**. Do not put real passwords, tokens, or private FTP users in commits.

- Dedicated host: `(set locally)`
- FTP / SFTP: port + user under hoster paths (e.g. `/ServerWorld`)
- Live INI name: e.g. `world.ini`
- RCON / Query / game ports: from hoster panel
- Game version on host: e.g. **42.20.x**

## Panel bugfix agent

- Screenshot reports: reproduce local (`python run_panel.py`) then test VPS; commits only on branch **`fix`**; merge after user readiness check. Protocol: `.cursor/rules/panel-bugfix.mdc`.

## Mod maker agent

- Create / pack / publish / catalog / FTP-deploy of PZ mods: commits only on branch **`mod`**; rebase onto `main`; merge after user readiness check. Protocol: `.cursor/rules/mod-maker.mdc`.
- Live custom loadout: 5 local Meatballs mods **plus KI5 garage A+B + support** (`damnlib` first among vehicles, bob Enter/Exit last). FTP as-is 2026-09-04. **Hoster JVM restart required.** QoL pack `3793101161` and Better Safehouse were **not** added.
- Deploy path: panel **Моды** (`apply-ini`) + **Workshop → Залить выбранные как есть**. Live INI **does not** write `WorkshopItems=` (`dedicated_workshop_items: false`) — hoster Steam workshop download crashes B42. Unified «Собрать» is not the Meatballs hotfix path (Lua hook conflicts).
- **Sprint 14:** вкладка Workshop ищет каталог Steam через `QueryFiles` (ключ `STEAM_WEB_API_KEY`). URL/ID — без ключа. «На сервер» = catalog + SteamCMD + FTP as-is + `Mods=`/`WorkshopItems=`. Рестарт JVM всё ещё у хостера.
- **WS 3793101161** «Meatballs Mods Pack» — это **один Workshop item** (склеенный пак), не Steam Collection. Скачан anonymous SteamCMD в `.mirror/meatballs-xl/`. Внутри 12 модов; LogExtender/ServerTweaker в каталоге остаются **local** (наши патчи). На живой FTP не заливал.
- **KI5 garage (2026-09-04):** Wave A + срез B + support (`YAPZLib`, `VVR`, mini-fixes, Seat UI, три фикса bob). 33 папки залиты as-is на FTP, `world.ini` Mods= 6→39. **`WorkshopItems=` emptied 2026-09-04:** XLGAMES Steam download of `damnlib` `3171167894` fails (`result=2`) then B42 `GameServerWorkshopItems.Install` NPE → `Server exited`. Mods stay on FTP; clients already have Workshop locally. Catalog flag `dedicated_workshop_items: false`. **Hoster JVM restart required.**
- **KI5 collection vehicles (2026-09-05):** из [Server Meatballs](https://steamcommunity.com/sharedfiles/filedetails/?id=3781417097) докачаны все item’ы с тегом Vehicles, которых ещё не было (21 машина + Specific Loot / Military Zones / Dismantle / Vehicle Market). FTP as-is, затем QoL-срез ниже. `WorkshopItems=` пустой. Клиент: папки в `Zomboid\mods` + Steam 108600.
- **Collection QoL (2026-09-05):** официальные WS (не пак `3793101161`): Common Sense, Ladders, Alert, errorMagnifier, Rain, MRE, Sun, PhunCure, Skully, Zero Weight Keys, Useful Barrels, 3D Gun Racks, Skill Recovery Journal, NVG (без VFE-патча), Open All Containers. 15 папок FTP as-is, `Mods=` 70→85, bob Enter/Exit last.
- **Collection caution (2026-09-05):** Proximity Inventory, LG Extended Plumbing, PhunZones 2. FTP as-is, then Better Safehouse stack below. `WorkshopItems=` пустой.
- **Better Safehouse + panel (2026-09-05):** official WS `3634569678` FTP as-is (not repacked). `MeatballsSafehouses` **1.3.0** finds houses by overlap after their expansion, notifies Better Safehouse clients on panel create/release. `Mods=` 88→89, order `AdminTools` → `VerifyPack315` → `BetterSafehouse` → `MeatballsSafehouses`. **Hoster JVM restart required.** Keep vanilla SafeHouse enabled in their sandbox; custom claim can stay off.
- Template `templates/mod/` is still unversioned; scaffold then move into `42/` until the template is upgraded.
- **Rating 1–40 local only (2026-09-05):** SteamCMD 42 WS items → `.mirror/meatballs-xl/mods` + `ServerWorld/mods` + `%USERPROFILE%\Zomboid\mods`. Catalog updated (official WS IDs, not pack `3793101161`). Local `world.ini` Mods= **89** = old KI5-A set + 50 new IDs, bob last, `WorkshopItems=` empty. **Live XLGAMES not FTP’d.** Panel `POST /api/local-server/start` → client GameServer 42.20.4, `*** SERVER STARTED ****`, smoke **PASS**. Loaded 84/89: skipped `VerifyPack315` (empty pack stub), `SpnHair` (`require=FH` / Fluffy Hair not installed), three TouchMeNot skins whose KI5 cars are not on this local INI. Vanilla mannequin/RoomDef errors only.
- **Rating 41–80 local only (2026-09-05):** second table minus SVU/Lifestyle/Firearms. Fluffy Hair `FH` before `SpnHair`. Dropped 5 new damnlib cars after `69chargerMakeTire` crash.
- **Start-compat local (2026-09-05):** TchernoLib + EasyConfigChucked (local `42/` shim — upstream has no B42 folder) + Alert + errorMagnifier. Climb/Crawl/Conditional-Speech load. BetterSafehouse, Common Sense, Ladders on local INI. Top-20 QoL from the third table. **Skipped:** VerifyPack315 stub; RV Interior base `3543229299` (breaks existing save); 85 Step Van / 86 CUCV / their TouchMeNot skins (`85chevyStepVanMakeTire` / missing `Base.93chevyK3500Tire2`, same class as 69charger). Smoke **PASS**, 148 mods loaded, vanilla mannequin/RoomDef only. **Live not FTP’d.**
- **Notepad list local (2026-09-05):** from Desktop URL dump. Safe wave 23 WS → 26 folders, kept one More Variety Loot (dropped 25/50/200%). Smoke **PASS**, 171 loaded. Caution wave 13 WS (skipped Item Condition `2852309899`, Tanks Have Propane `3676347667`, Tactical Pistol Hold `3680633169`); dropped FunctionalGuttersRemoved + StarvingZombiesWIP. Smoke **PASS**, 185 loaded, `*** SERVER STARTED ****`, no NPE/WD/required-mod. Cachedir `.mirror/meatballs-xl/ServerWorld`. **Live not FTP’d.** Do not add ETO/VFE/Lifestyle/old Common Sense/outdated/NPC SP/Necroa/Tomb body/grenades/silencers/basements.
- **Workshop bundles (2026-09-05):** as-is folders (not Lua merge) in `.cache/workshop-packs/`: required Libraries / Core / KI5 / Character / Gameplay; optional Audio (`SHdynamicmusic`, not in server `Mods=`). Rebuild: `python tools/pack_server_bundles.py`. Steam upload not done (needs Guard + `STEAM_PASSWORD`). **Live not FTP’d.**
- **Unified five ids (2026-09-05, new world):** `python tools/pack_unified_five.py` → `MeatballsLibraries` `MeatballsCore` `MeatballsKI5` `MeatballsCharacter` `MeatballsGameplay` (BetterSafehouse inside Core). Local test `-servername pack5` (`Server/pack5.ini`), cachedir meatballs-xl. Smoke **PASS**, loaded 5/5, `*** SERVER STARTED ****`, no NPE/WD/MakeTire. ~9k last-wins overwrites inside packs (some UI patches dropped). Audio still optional / not in `Mods=`. `world.ini` 184-id loadout left intact. **Live not FTP’d.** Steam not published.
- **Workshop stage (2026-09-05):** Steam: **1/5 Libraries** [3796197817](https://steamcommunity.com/sharedfiles/filedetails/?id=3796197817), **2/5 Core** [3796206775](https://steamcommunity.com/sharedfiles/filedetails/?id=3796206775), **3/5 KI5** [3796212345](https://steamcommunity.com/sharedfiles/filedetails/?id=3796212345), **4/5 Character** [3796217229](https://steamcommunity.com/sharedfiles/filedetails/?id=3796217229). Next: **5/5 Gameplay** (`C:\Users\zvaa\Zomboid\Workshop\MeatballsGameplay`, Required = Libraries). Descriptions list included mods (Steam 8000-char cap). Catalog `src/modpacks/meatballs-five.catalog.json`. Do not write these ids to live `WorkshopItems=`. **Live not FTP’d.**

## Panel

- Product: `docs/PRODUCT.md`. Onboarding: `docs/ONBOARDING.md`. **Now: Sprint 14** — каталог Steam Workshop в панели (3.25.0)
- Start: desktop shortcut **MEATBALLS PZ Panel** → `launch_panel.bat` → `python run_panel.py` (http://127.0.0.1:8000/; next free port if 8000 is an old process)
- Panel **3.24.3** (branch `fix`, on `main`): `api()` keeps CSRF + `Content-Type` when `apiStepUp` adds confirm headers. Stock 3.24.2 wizard Save on public VPS returned 403 CSRF, then 422 if Content-Type was dropped.
- Test VPS **2026-09-04**: `185.221.154.241:8000` health **3.24.2** after one-shot `deploy_vps.sh`; compose has docker.sock + `/host/pz-panel` for later in-panel updates. VPS active profile **MEATBALLS** (`meatballs`, XLGAMES, process `none`).
- Panel **3.26.4** (local WIP, not this commit): FTP `timed out` на одном файле больше не ставит весь Pull на паузу. `run_panel.py` без `--reload`.
- Panel **3.26.3**: статус зеркала не делает полный обход диска на каждый файл Pull.
- Panel **3.26.2**: Pull больше не встаёт на паузу из‑за `550` на живом `DebugLog-*.txt`.
- Panel **3.26.1**: главная и Зеркало больше не ждут живой FTP + вложенный RCON.
- Panel **3.26.0**: Приваты — зум до домов, синие точки онлайн из дампа мода.
- Panel **3.25.0**: Workshop search/resolve/from-steam. Key: `STEAM_WEB_API_KEY` in `.env`.
- Panel **3.24.2**: Update button on Docker chooses rebuild (sock + project mount), not Windows setup.exe. Release: https://github.com/telharr/meatballs/releases/tag/v3.24.2
- Panel **3.24.1**: wizard «Сохранить и сделать активным» uses in-app step-up (not `window.prompt`); errors show in the wizard; `/api/status` no longer paints `[500]` when no profile
- Panel **3.24.0**: Приваты рисуют бумажный атлас из `worldmap.xml` (`python tools/knox_atlas.py`). PNG gitignore.
- Panel **3.22.2**: navbar version badge; boot force-check; 5‑min update cache; `PANEL_GITHUB_TOKEN`; `packaging/deploy_vps.sh`

## What still needs a human

- **Rotate VPS root password** (was reused from older chat for deploy)
- Hoster restart after RCON `quit` — process.kind=`none`. **MeatballsSafehouses 1.2.0** (online XY in dump) needs **Залить мод** + JVM restart. Live test zone `MB-panel-probe` 10648,6912 8×8.
- Pull `_admin.txt` / `_cmd.txt` into mirror so Admin Audit has rows
- Do not commit `.env` or `panel/backups/*`

## Dedicated on this PC

- Optional: set `PZ_DEDICATED_DIR` in `.env`
- Client GameServer path is machine-specific — do not hardcode in shared docs
- Local smoke 2026-09-05: panel http://127.0.0.1:8000/ started GameServer `-cachedir=.mirror/meatballs-xl/ServerWorld` `-nosteam` `-Xmx3072m`. Log `ServerWorld/Logs/2026-09-05_15-38_DebugLog-server.txt`. Stop: panel or `python tools/local_server.py stop`.
- **Player-sim QA 2026-09-05 16:25 (no client):** RCON 127.0.0.1:16284, 0 online. `adduser Tester` + admin OK; rain/chopper/gunshot/save OK; `additem`/`addvehicle`/`createhorde`/`teleport` need an in-world body. Boot 118/125. Cachedir `MeatballsSafehouses` is stub (`42/mod.info` only, no Lua) — panel create cmd not consumed. Leftover `mb_admintools_cmd.txt` citywipe March Ridge **cleared** before ticks. Skip: VerifyPack315 stub; Climb/Crawl (`TchernoLib`); Conditional-Speech; RVInteriorExpansion; two POB skins without parent cars. Collection QoL / BetterSafehouse **not** on this local `Mods=`. Vanilla mannequin + `help` translation `%1$s` (`UI_ServerOptionDesc_SetLogLevel`) only. Account **Tester** waiting for a client join (`-nosteam`, `127.0.0.1`, ports 16281/16282).

## Tools to prefer

- FTP: `tools/ftp_client.py`, `tools/ftp_manager.py`
- Catalog apply: `POST /api/mods/apply-ini` or `tools/mod_catalog.py`
- Local dedi: `python tools/local_server.py status|start|stop`
- Safehouses: panel **Приваты**, `src/mods/MeatballsSafehouses`
