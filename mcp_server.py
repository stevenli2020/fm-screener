import os
import subprocess
from fastmcp import FastMCP

mcp = FastMCP("FM")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

@mcp.tool()
def read_project_file(relative_path: str) -> str:
    """Read the contents of any project file (e.g., HANDOFF.md, src/core/ingestion.py)."""
    full_path = os.path.normpath(os.path.join(PROJECT_ROOT, relative_path))
    if not os.path.exists(full_path):
        return f"Error: File '{relative_path}' does not exist."
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

@mcp.tool()
def write_project_file(relative_path: str, content: str) -> str:
    """Create or overwrite a file in the workspace (e.g., scripts/test.bat or src/module.py)."""
    full_path = os.path.normpath(os.path.join(PROJECT_ROOT, relative_path))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} bytes to '{relative_path}'."

@mcp.tool()
def run_pytest(test_target: str = "tests/") -> str:
    """Run pytest suite inside the Windows/Linux .venv environment and return test outputs."""
    # Handle cross-platform virtual environment layout differences
    if os.name == "nt":
        venv_pytest = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "pytest.exe")
        creation_flags = subprocess.CREATE_NO_WINDOW
    else:
        venv_pytest = os.path.join(PROJECT_ROOT, ".venv", "bin", "pytest")
        creation_flags = 0

    # Fallback to system pytest if venv version isn't present
    if not os.path.exists(venv_pytest):
        venv_pytest = "pytest"

    try:
        result = subprocess.run(
            [venv_pytest, test_target, "-v"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags
        )
        return f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return f"Execution error: {str(e)}"

@mcp.tool()
def run_command(command: str) -> str:
    """Execute a command or script in Windows PowerShell/Bash inside the project root directory."""
    try:
        env = os.environ.copy()
        
        # Configure shell, environmental paths, and flags dynamically based on the OS
        if os.name == "nt":  # Windows
            venv_scripts = os.path.join(PROJECT_ROOT, ".venv", "Scripts")
            path_separator = ";"
            shell_args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
            creation_flags = subprocess.CREATE_NO_WINDOW
        else:  # Linux / macOS
            venv_scripts = os.path.join(PROJECT_ROOT, ".venv", "bin")
            path_separator = ":"
            shell_args = ["/bin/bash", "-c", command]
            creation_flags = 0

        # Inject virtual environment binaries folder into system PATH
        if os.path.exists(venv_scripts):
            current_path = env.get("PATH", "")
            env["PATH"] = f"{venv_scripts}{path_separator}{current_path}" if current_path else venv_scripts

        result = subprocess.run(
            shell_args,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True, 
            timeout=120,
            creationflags=creation_flags
        )
        return f"EXIT CODE: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        return f"Execution error: {str(e)}"

if __name__ == "__main__":
   mcp.run()
