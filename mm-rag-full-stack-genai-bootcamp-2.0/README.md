# Multimodal RAG Full-Stack GenAI Bootcamp

This repository is the workspace for a full-stack Generative AI bootcamp project focused on multimodal Retrieval-Augmented Generation (RAG). The project will combine document ingestion, retrieval, and generative AI components with a user-facing application.

> The project is currently in its initial setup stage. Application source code and dependencies will be added as the bootcamp progresses.

## Project Goals

- Build an end-to-end multimodal RAG application.
- Process and retrieve information from multiple content types.
- Use retrieved context to produce grounded AI responses.
- Connect the AI workflow to a full-stack application.
- Keep the Python environment and dependencies reproducible.

## Prerequisites

Install the following before setting up the project:

- [uv](https://docs.astral.sh/uv/)
- Git
- Python 3.12, installed directly or managed by uv

This project uses Python 3.12.

## Python and Virtual Environment Setup

### 1. List available Python versions

Use uv to display Python installations found on your machine and Python versions available for download:

```bash
uv python list
```

By default, uv displays installed Python interpreters and the latest downloadable patch release for each supported Python minor version.

To display older patch releases as well, run:

```bash
uv python list --all-versions
```

To show only Python 3.12 versions, run:

```bash
uv python list 3.12 --all-versions
```

### 2. Install Python 3.12 if needed

If Python 3.12 is not installed, let uv install the latest available Python 3.12 patch release:

```bash
uv python install 3.12
```

Verify that uv can find it:

```bash
uv python find 3.12
```

### 3. Create the virtual environment

From the project root, create a virtual environment named `env` with Python 3.12:

```bash
uv venv env --python 3.12
```

The general command format is:

```bash
uv venv env --python <python-version>
```

For example, an exact Python patch version can be requested with:

```bash
uv venv env --python 3.12.11
```

If the requested interpreter is not already installed, uv normally downloads a compatible managed Python build automatically when one is available.

### 4. Activate the virtual environment

On macOS or Linux Terminal:

```bash
source env/bin/activate
```

On Windows Terminal or Command Prompt:

```bat
env\Scripts\activate.bat
```

### 5. Verify the active Python version

```bash
python --version
```

The output should report Python 3.12.x.

You can also confirm which interpreter is active on macOS or Linux:

```bash
which python
```

It should point to the `env/bin/python` executable inside this project.

## Install Project Dependencies

After activating the virtual environment, install the dependencies listed in `requirements.txt`:

```bash
uv pip install -r requirements.txt
```

The dependency file is currently empty and will be updated as packages are introduced.

## Typical Setup Workflow

Run these commands after cloning the repository:

```bash
git clone <repository-url>
cd mm-rag-full-stack-genai-bootcamp-1.0
uv python list
uv python install 3.12
uv venv env --python 3.12
source env/bin/activate
uv pip install -r requirements.txt
python --version
```

If Python 3.12 is already installed, `uv python install 3.12` is optional.

## Environment Variables

Store local API keys and configuration values in a `.env` file. Never commit secrets to version control.

Example:

```dotenv
# Add project-specific environment variables here.
# API_KEY=your-api-key
```

## Deactivate the Environment

When you finish working on the project, leave the virtual environment with:

```bash
deactivate
```

## Repository Structure

```text
.
├── README.md          # Project documentation and setup instructions
├── requirements.txt  # Python dependencies
└── .env               # Local environment variables (not committed)
```

The structure will expand as backend, frontend, ingestion, retrieval, and evaluation components are implemented.
