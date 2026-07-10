# Architecture Review

## Current Strengths

- The project has a clean `src/` layout with explicit runtime and development dependencies.
- The domain model covers the key BI governance assets: workspaces, users, reports, semantic models, data sources, refreshes, permissions, checks, results, and findings.
- Seed data is deterministic and intentionally includes governance problems, which makes tests repeatable.
- The rules engine returns normalized findings with clear evidence and recommendations.

## Architectural Weaknesses Found

- The application originally had no public boundary for rule execution or findings retrieval, which would have forced future UI code to import service internals.
- Test database setup was duplicated across several test modules, making future configuration changes easy to miss.
- Time defaults used deprecated naive `datetime.utcnow()` calls.
- Findings persistence used a database table but had no API or CLI workflow around it.
- The project does not yet have migrations, so schema evolution will become risky once data needs to survive between versions.
- The rules engine is acceptable for a local lab, but larger datasets will need more aggregate SQL queries and fewer relationship-level scans.
- The Streamlit UI is now present, but it should eventually be split into smaller page modules as interaction complexity grows.
- There is no authentication, authorization, pagination, or multi-environment deployment story yet.

## Implemented Improvement Plan

1. Established a local Git baseline, using `work/repo.git` because the workspace `.git` directory is a locked placeholder.
2. Added FastAPI governance endpoints for running rules and listing findings.
3. Added Pydantic response schemas to make API contracts explicit.
4. Added a CLI command for running governance rules outside the API.
5. Centralized test database configuration in one pytest fixture.
6. Replaced deprecated UTC defaults with a shared helper.
7. Updated README usage and architecture notes.

## Recommended Next Steps

- Add Alembic migrations before the schema grows further.
- Move rule metadata into a registry so rules can be enabled, disabled, grouped, and documented from one place.
- Add pagination and summary endpoints for findings, especially before building the UI.
- Add aggregate SQL implementations for high-volume rules such as refresh failure rates and score thresholds.
- Store finding evidence in a native JSON column for databases that support it, with SQLite compatibility retained.
- Split the Streamlit app into page modules and add screenshot-based UI smoke tests.
- Add CI that runs `ruff format --check`, `ruff check`, and `pytest`.
