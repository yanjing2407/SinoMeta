# Repository Guidelines

## Project Structure & Module Organization

This is a flat Python/FastAPI project. Core calculation modules live at the repository root: `bazi.py`, `qimen.py`, `liuyao.py`, `meihua.py`, `calendar_utils.py`, and `integrate.py`. `main.py` exposes the FastAPI app and API routes. `llm_store.py` manages SQLite-backed LLM provider and role configuration. Browser assets are in `static/` (`index.html`, `admin.html`). Tests currently live in `test_core.py`. Reference notes are under `docs/`, and generated/runtime data belongs in ignored folders such as `data/` and `result/`.

## Build, Test, and Development Commands

Create or refresh a local environment, then install runtime dependencies:

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Run the app locally:

```powershell
python main.py
```

`main.py` starts Uvicorn and selects a free port from `8000` upward. On Windows, `start.bat` is an alternate launcher that opens `http://localhost:8000` and falls back to `8001` if needed.

Run the core regression checks:

```powershell
python test_core.py
```

## Coding Style & Naming Conventions

Use UTF-8 source files, 4-space indentation, and Python `snake_case` for modules, functions, and variables. Keep domain calculation logic in the existing focused modules; route handling and request/response models belong in `main.py`. Prefer explicit dictionaries/lists for structured divination results, and convert non-JSON values through `make_serializable` before returning API responses.

## Testing Guidelines

Add regression tests to `test_core.py` or split into new `test_*.py` files if the file grows. Name tests `test_<behavior>` and keep assertions concrete, especially around calendar boundary cases, true solar time offsets, and generated chart fields. Run `python test_core.py` before submitting calculation changes.

## Commit & Pull Request Guidelines

Git history is minimal; keep commits short and scoped. A `type: summary` style is acceptable, for example `fix: correct qimen day offset` or `style: render parsed LLM output`. Pull requests should describe user-visible behavior, list commands run, mention any data/schema changes, and include screenshots when changing `static/` pages.

## Security & Configuration Tips

Do not commit API keys, local databases, or generated results. For non-local admin access, set `SINOMETA_ADMIN_TOKEN`. Override the SQLite path with `SINOMETA_DB_PATH` when a test or deployment needs isolated storage.
