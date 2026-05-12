# Preprocessing

Repo-specific instructions for the desktop data preprocessing tool.
Use `/Users/mk/AGENTS.md` for global safety and environment rules.

## Overview
- Desktop GUI for Excel/CSV time-series preprocessing.
- Windows entrypoint: `gui_app.py` (tkinter).
- macOS entrypoint: `gui_app_mac.py` (PyQt5).
- Core value: filter, outlier handling, timestamp normalization, validation-data generation.

## Read First
1. `README.md` — user flow, commands, build notes
2. `MANUAL.md` — detailed user manual
3. `CHANGELOG.md` — recent behavior changes

## Working Areas
- `data_preprocessor.py` — preprocessing logic
- `preset_manager.py` — preset save/load/import/export
- `gui_app.py` — Windows GUI
- `gui_app_mac.py` — macOS GUI
- `test_time_norm.py` — timestamp normalization test
- `.github/workflows/build.yml` — CI build behavior

## Source-of-Truth Rules
- Keep preprocessing behavior in `data_preprocessor.py`, not duplicated in UI.
- Preserve `*_prepro.xlsx`, `*_prepro_with_valid.xlsx`, and `*_valid.xlsx` naming conventions.
- Validation-data generation must continue to depend on removed rows from preprocessing.
- Windows and macOS GUI entrypoints may differ; keep platform-specific behavior explicit.

## Commands
```bash
# install runtime deps
python -m pip install -r requirements.txt

# install build deps
python -m pip install -r build_requirements.txt

# run Windows GUI
python gui_app.py

# run macOS GUI
python gui_app_mac.py

# run timestamp normalization test
# uses lowercase second-frequency syntax (`61s`) to avoid pandas warnings
python test_time_norm.py

# run static lint
python -m ruff check .

# build Windows EXE
pyinstaller --noconfirm --clean DataPreprocessor_windows.spec
```

## Workflow Model
- Small UI fix or logic tweak: implement directly, then verify with the lightest applicable command.
- Medium change that affects multiple modules: use `$plan`.
- Broad refactor or packaging/workflow change: use `$ralplan` before implementation.

## Agent Rules
- Prefer minimal fixes in `data_preprocessor.py` for core logic and in `gui_app*.py` for presentation issues.
- Update `MANUAL.md` when user-visible behavior changes.
- Keep generated artifacts and sample data out of the edit path unless the task is specifically about them.
- Do not add dependencies without clear need.
- Preserve backward compatibility for saved presets unless explicitly told otherwise.

## Gotchas
- `PyQt5` is required for `gui_app_mac.py`.
- GitHub Actions uses Python 3.11 for builds.
- Python 3.11 is the recommended local environment.
- `developer_info.json` overrides `version.py` metadata when present.
- `test_time_norm.py` is useful as a local benchmark/reference. It uses lowercase pandas second-frequency syntax (`61s`) to avoid the deprecated uppercase alias warning.

## Done When
- requested behavior works on the relevant platform
- verification evidence is collected
- user-facing docs are updated when behavior changes
- changed files are listed in the final report
