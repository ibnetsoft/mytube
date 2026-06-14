# Test Suite

Run the fast regression tests with:

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

These tests avoid external AI/API calls and focus on guardrails that should stay stable:

- Autopilot duplicate-run prevention and queue state reporting
- Settings-page permission checks for standard members
- Settings-page JavaScript extraction safety

Files under `_dev` and `scratch` are manual diagnostics and are not part of the automated test suite.
