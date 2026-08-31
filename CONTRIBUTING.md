# Contributing

Thank you for contributing to this Project Zomboid modding workspace.

## Commit Standards

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

### Types

| Type | Use |
|------|-----|
| `feat` | New mod feature or tool capability |
| `fix` | Bug fix in mod logic or tooling |
| `docs` | Documentation only |
| `refactor` | Code change without behavior change |
| `chore` | Build, CI, dependencies |
| `test` | Tests |

### Scopes

- `mod:<ModName>` — Individual mod changes (e.g. `feat(mod:MyMod): add crafting recipe`)
- `tools` — Python tooling
- `ci` — GitHub Actions
- `docs` — Architecture and guides

### Examples

```
feat(mod:SurvivalPack): add hunger decay on hourly tick
fix(tools): detect tiledef collisions in nested directories
docs(architecture): document OnServerCommand flow
chore(ci): add luacheck to deploy workflow
```

## Development Workflow

1. Create a mod under `src/mods/<ModName>/` with a valid `mod.info`.
2. Place Lua in `media/lua/client|server|shared/` per the architecture guide.
3. Run `luacheck src/mods/` before committing.
4. For modpacks, run `python tools/pack_merger.py --fail-on-conflict`.
5. Open a PR with a clear description and test notes.

## Multiplayer Safety Checklist

- [ ] World mutations only in `server/` scripts
- [ ] All `OnServerCommand` handlers validate player and args
- [ ] Nil-checks on `IsoPlayer`, `IsoGridSquare`, `InventoryItem`
- [ ] ModData keys prefixed with mod ID
- [ ] No hardcoded tiledef numbers that conflict with vanilla (vanilla uses low ranges)

## Pull Request Guidelines

- Keep PRs focused — one mod or one tool change per PR when possible.
- Include reproduction/testing steps for gameplay changes.
- Do not commit Steam credentials, `.env` files, or Workshop VDF with passwords.
