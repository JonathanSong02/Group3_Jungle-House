# Jungle House AI Wiki Assistant

[![CI](https://github.com/JonathanSong02/Group3_Jungle-House/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/JonathanSong02/Group3_Jungle-House/actions/workflows/ci.yml)

| Folder | What it is |
|---|---|
| `jungle-house-wiki-ai/` | React + Vite frontend (deployed on Vercel) |
| `backend/` | Flask backend (deployed on Railway) and the database tools in `backend/tools/` |
| `mysql/`, `backend/migrations/` | SQL scripts and schema migrations ([docs](docs/database-migrations.md)) |

## Automatic checks (CI)

Every push to any branch, and every pull request to `main`, runs two independent jobs on GitHub
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). A green check means both passed; a red cross means
something broke.

| Job | Steps |
|---|---|
| **Backend tests (Python 3.12)** | install the test dependencies, then `python -m unittest discover -s . -p "test_*.py"` in `backend/src` |
| **Frontend lint, tests and build (Node 22)** | `npm ci`, `npm run lint`, `node --test "src/**/*.test.js"`, `npm run build` in `jungle-house-wiki-ai` |

* The backend tests use an in-memory SQLite adapter. They need no database, no network and no secrets. CI sets a
  **dummy** `FLASK_SECRET_KEY` (the app refuses to import without one) and turns the Notion background thread off.
* CI installs only the small set of packages the tests import ([`backend/requirements-ci.txt`](backend/requirements-ci.txt));
  versions still come from `backend/requirements.txt`. torch and sentence-transformers are not installed.
* Lint fails on errors only. The 11 known warnings are printed but do not fail the job.
* Some tests are skipped on purpose when a local-only file is missing (the production schema snapshot,
  `schema_production.json`, which is never committed). CI shows them as `skipped`.
* A separate workflow, [`dependency-audit.yml`](.github/workflows/dependency-audit.yml), runs `npm audit` and
  `pip-audit` once a week and on demand. It only reports, and never runs on a push or a pull request.

### Run the same checks on your computer (PowerShell)

```powershell
# Backend (from the repository root). The key is a dummy, only for the tests; no database is needed.
cd backend\src
.\venv\Scripts\Activate.ps1
$env:FLASK_SECRET_KEY = "dummy-local-test-key-0123456789-0123456789"
$env:NOTION_AUTO_SYNC_ENABLED = "false"
python -m unittest discover -s . -p "test_*.py"        # add -v to name every test, -b to hide log noise of passing tests
python -m unittest test_notion_sync_dedupe -v           # or just one test file

# Frontend
cd ..\..\jungle-house-wiki-ai
npm ci
npm run lint
node --test "src/**/*.test.js"
npm run build
```

### Reading a failed run

1. Open the **Actions** tab (or click **Details** next to the red cross on the pull request) and open the run.
2. The failed job and step have a red cross. Click the step to expand its log.
3. Backend: look for `FAIL: test_name (test_file.Class.test_name)` followed by the traceback.
   Frontend: lint prints `file:line  error  rule`; unit tests print `not ok <n> - <test name>`; a build prints the error.
4. Fix it, push again: the run restarts and the older run for that branch is cancelled.

Pushing to a branch that has an open pull request starts two runs (one for the push, one for the pull request).
That is expected.

Maintainers: to stop broken changes from being merged, require the two checks under
*Settings → Branches → Branch protection rules → Require status checks to pass* (`Backend tests (Python 3.12)` and
`Frontend lint, tests and build (Node 22)`).
