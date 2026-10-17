# EnterpriseFlow

An enterprise workflow and approval API built with Python and FastAPI.

## Features

- Health endpoint
- Automated API tests
- API documentation
- Modular project structure

## Local setup

Create and activate a virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate

Install dependencies:

    python -m pip install "fastapi[standard]" pytest httpx ruff

Run tests:

    python -m pytest -q

Start the development server:

    fastapi dev app/main.py

Open the API documentation at:

    http://127.0.0.1:8000/docs