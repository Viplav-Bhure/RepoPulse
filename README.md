# RepoPulse

An AI-powered repository intelligence platform that analyzes public GitHub repositories using source-code metrics, static analysis, Git history, machine learning, and evidence-grounded LLM explanations.

See [`docs/`](docs/) for full product and architecture documentation.

Status: Phase 1 complete (v0.1); Phase 2 - Analysis Core next (not started)

## Running the backend tests

Use a throwaway PostgreSQL 17 container, never the Compose database:

```powershell
docker run --rm -d --name repopulse-test-pg -e POSTGRES_DB=repopulse_test -e POSTGRES_USER=repopulse_test -e POSTGRES_PASSWORD=<throwaway> -p 127.0.0.1:55432:5432 postgres:17
```

Wait for `pg_isready`, then set `TEST_DATABASE_URL` to
`postgresql+psycopg://repopulse_test:<throwaway>@127.0.0.1:55432/repopulse_test`
and `REQUIRE_TEST_DATABASE=1` for the current process. From `backend`, run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Stop the container with `docker stop repopulse-test-pg`, clear both variables,
and verify with `docker ps`.
