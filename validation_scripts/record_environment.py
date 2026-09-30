import importlib.metadata as metadata
import json
import platform
import sqlite3
import sys
from pathlib import Path

packages = ["torch", "torchvision", "torchaudio", "monai", "numpy", "langchain", "langchain-core", "langgraph", "langgraph-checkpoint", "langgraph-checkpoint-sqlite", "langchain-openai", "langchain-community", "chromadb", "fastapi", "starlette", "pydantic", "pytest", "sentence-transformers", "transformers"]
record = {"python_path": sys.executable, "python_version": platform.python_version(), "conda_env": "medical_ai_agent", "sqlite": sqlite3.sqlite_version, "packages": {name: metadata.version(name) for name in packages}}
Path(__file__).with_name("environment.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record, indent=2))
