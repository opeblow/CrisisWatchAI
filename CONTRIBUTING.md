# Contributing to CrisisWatch AI

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/CrisisWatchAI.git
   cd CrisisWatchAI
   ```
3. **Create a branch** for your change:
   ```bash
   git checkout -b feat/my-new-feature
   ```
4. **Follow the [Quickstart](README.md#-quickstart)** to set up your dev environment

## Development Workflow

### Backend (Python)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite+aiosqlite:///./crisiswatch.db
python seed_demo.py
uvicorn main:app --reload --port 8000
```

Run the smoke test before submitting:
```bash
python smoke_test.py
```

### Frontend (TypeScript)

```bash
cd frontend
npm install
npm run dev
```

Run the build (includes typecheck + lint) before submitting:
```bash
npm run build
```

## Code Style

### Python
- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints on all function signatures
- Async/await for all database and HTTP operations
- Use Pydantic models for API request/response validation
- Keep functions focused — one responsibility per function

### TypeScript
- Use strict TypeScript (no `any` unless absolutely necessary)
- Prefer functional components with hooks
- Use the existing UI primitives in `components/ui/`
- All API calls go through `lib/api.ts`

### General
- No hardcoded secrets, keys, or credentials
- No commented-out code in PRs
- Write meaningful commit messages

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add user authentication endpoint
fix: resolve forecast date parsing error
docs: update API reference in README
refactor: simplify alert severity scoring
test: add smoke test for report generation
```

## Pull Request Process

1. **Ensure all checks pass:**
   - Backend: `python smoke_test.py`
   - Frontend: `npm run build`
2. **Update documentation** if your change affects the API or project structure
3. **Keep PRs focused** — one feature or fix per PR
4. **Fill out the PR template** with a clear description of what changed and why
5. **Request a review** from a maintainer

## Adding a New Data Source

1. Create a new adapter in `backend/data/sources/`:
   ```python
   # backend/data/sources/my_source.py
   from data.sources.base import BaseSource

   class MySource(BaseSource):
       async def fetch(self) -> list[CrisisEvent]:
           ...
   ```
2. Register it in `backend/data/ingestion.py`
3. Add tests in `backend/smoke_test.py`

## Adding a New ML Model

1. Create the model module in `backend/ml/`
2. Implement a graceful fallback (the project convention)
3. Expose it via a router in `backend/routers/`
4. Add frontend support in `frontend/lib/api.ts` and a UI panel

## Reporting Bugs

Open a [GitHub Issue](https://github.com/YOUR_USERNAME/CrisisWatchAI/issues) with:
- Clear title and description
- Steps to reproduce
- Expected vs actual behaviour
- Environment details (OS, Python version, Node version)

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

## Questions?

Open a discussion or reach out to the maintainers. We're happy to help!
