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

## Local MinIO service

For local CT upload, image analysis, and viewer verification, use the installed
Windows MinIO executable below. Do not use the unsupported `minio.exe` stored
at the repository root.

```powershell
E:\moani\minio\minio.exe server .\data\minio --address ":9000" --console-address ":9001"
```

Run the command from the repository root. The S3 endpoint is
`http://127.0.0.1:9000` and the console is `http://127.0.0.1:9001`.

## Martin development skills

Project development skills are versioned under `.agents/skills/`. Before changing
a Martin subsystem, read the matching `SKILL.md`; load more than one for
cross-cutting work. Start with `martin-quality-runtime` when a task includes
verification or release readiness, then load the core subsystem skill, then the
Web or reporting skill if applicable.

| Task area | Required skill |
| --- | --- |
| Agent, prompt, tools, CaseContext, sessions, audit/source policy | `martin-agent-policy` |
| Knowledge documents, loaders, Chroma, retrieval, provenance | `martin-rag-knowledge` |
| CT upload, MinIO, NIfTI/MetaImage, MONAI detection | `martin-vision-pipeline` |
| FastAPI, Vue/Pinia, REST/WebSocket, workstation, case restore | `martin-web-workstation` |
| Report prompts, report generation, evidence and fallback templates | `martin-reporting` |
| Tests, builds, runtime configuration, privacy/logging review | `martin-quality-runtime` |

These are engineering workflows for Codex and contributors. They do not create
Martin runtime clinical plugins or user-facing skills.
