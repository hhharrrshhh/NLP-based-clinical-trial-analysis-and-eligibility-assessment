# Experimental Python 3.14 setup

The default `requirements.txt` and `requirements-lock-windows.txt` describe the project's previously verified Python 3.11 environment. Do not use those pinned dependency sets unchanged with Python 3.14.

This experimental path keeps the original environment files intact and uses `requirements-py314.txt`, allowing pip to select package releases that publish Python 3.14-compatible wheels. PyTorch is installed first from its CPU wheel index to avoid pulling CUDA runtimes unnecessarily.

From the repository root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup-py314.ps1
.\scripts\start.ps1
```

Open the frontend at http://127.0.0.1:8501 and API docs at http://127.0.0.1:8000/docs. Verify with:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\smoke.ps1 -Full
```

## Important limitations

This is a compatibility experiment, not a tested or guaranteed Python 3.14 port. Newer versions of NumPy, pandas, scikit-learn, Transformers, Streamlit, FAISS, and their transitive dependencies may expose behavior or API changes. The dependency resolver succeeding does not prove the application works. If installation succeeds but tests fail, preserve the complete error output and fix compatibility issues before using the app.

The setup script creates `.venv` and installs into that folder. If you already have a partial `.venv`, remove it first only if it contains no environment you need to keep; then rerun the setup script. The existing Python 3.11 instructions and pinned requirements remain the recommended reproducible setup until Python 3.14 tests pass.
