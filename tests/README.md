# Tests

Tests are grouped by feature under `tests/`. Run the full suite with:

```bash
uv run pytest
```

The offline suite excludes tests that require network access, browsers, a graphical desktop, or opt-in memory checks:

```bash
uv run pytest -m "not network and not browser and not gui and not memory"
```
