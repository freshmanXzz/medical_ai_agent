# Project agent instructions

## Python test environment

Run all Python tests, syntax checks, and test-related commands with the shared
Conda environment below. Do not use the system Python or `.venv` for project
verification unless the user explicitly asks for it.

```powershell
E:\conda\envs\monai_learning\python.exe
```

Use the repository test wrapper whenever possible:

```powershell
.\scripts\run_tests.ps1
```

The wrapper accepts normal pytest arguments, for example:

```powershell
.\scripts\run_tests.ps1 tests\test_web_api.py -q
```
