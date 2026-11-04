"""One Python sandbox for every model under test (--sandbox local).

Each provider's own code tool is a different environment: Anthropic's container keeps the task files under their
names and allows a long tool loop; Vertex AI's built-in code execution renames attached files, limits each run to
30 seconds and ends a request after about 20 runs. Comparing models across those environments mixes the sandbox
into the score. With --sandbox local every model gets the same tool, run_python, which runs its code here, in a
fresh folder that holds the task's input files under their own names, with the same time limit and turn limit.

Safety: the code a model writes runs on this machine. It runs as a separate process in the task folder, with an
environment that holds no API keys, and on macOS inside sandbox-exec with the network denied and writes allowed
only in the task folder and the system temp folders. Where sandbox-exec is not available the run refuses unless
EEH_UNSAFE_SANDBOX=1 is set (for tests and Linux containers that are themselves isolated).

    python3 -m harness.sandbox      checks this machine: runs code, reads a task file, and confirms that network
                                    and writes outside the folder are blocked. Free: no model is called.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

TOOL_NAME = "run_python"
TIMEOUT = 120  # seconds per call
MAX_OUT = 20000  # characters of output returned to the model per call
DESCRIPTION = (
    "Run a Python 3 program and get back what it prints (stdout and stderr). The program runs in the task's working "
    "folder, which holds the task's input files under their own names (open them by name, e.g. pandas.read_csv('x.csv')). "
    "Each call is a new process: save results to files in the folder if a later call needs them. The standard library "
    "is available, and numpy, pandas, scipy and matplotlib where installed. No network. Time limit "
    f"{TIMEOUT} seconds per call.")
_PARAMS = {"type": "object", "properties": {"code": {"type": "string", "description": "the Python program to run"}},
           "required": ["code"]}
CLAUDE_TOOL = {"name": TOOL_NAME, "description": DESCRIPTION, "input_schema": _PARAMS}
GEMINI_DECL = {"name": TOOL_NAME, "description": DESCRIPTION, "parameters": _PARAMS}

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_PROFILE = """(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{ws}") (subpath "/private/tmp") (subpath "/private/var/folders") (literal "/dev/null")
       (literal "/dev/tty") (literal "/dev/dtracehelper"))
"""


def isolation():
    """'sandbox-exec', 'unsafe' (EEH_UNSAFE_SANDBOX=1) or None (refuse)."""
    if sys.platform == "darwin" and os.path.exists(SANDBOX_EXEC):
        return "sandbox-exec"
    if os.environ.get("EEH_UNSAFE_SANDBOX") == "1":
        return "unsafe"
    return None


class Workspace:
    """A fresh folder with the task files; run(code) runs one program there. Use as a context manager."""

    def __init__(self, files, log=None):
        self.mode = isolation()
        if not self.mode:
            raise RuntimeError("no process sandbox on this machine (sandbox-exec is macOS only); "
                               "set EEH_UNSAFE_SANDBOX=1 only inside an isolated container")
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="eeh-ws-"))
        for p in files:
            shutil.copy2(p, os.path.join(self.dir, os.path.basename(p)))
        os.makedirs(os.path.join(self.dir, ".tmp"), exist_ok=True)
        self.log, self.calls = log, 0
        if log:
            log({"kind": "workspace", "files": sorted(os.listdir(self.dir)), "isolation": self.mode})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _env(self):
        py_dir = os.path.dirname(os.path.realpath(sys.executable))
        return {"PATH": f"{py_dir}:/usr/bin:/bin", "HOME": self.dir, "TMPDIR": os.path.join(self.dir, ".tmp"),
                "MPLBACKEND": "Agg", "MPLCONFIGDIR": os.path.join(self.dir, ".tmp"), "LANG": "en_US.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}

    def run(self, code, timeout=TIMEOUT):
        """Run one program; returns the text the model sees (never raises)."""
        self.calls += 1
        script = os.path.join(self.dir, ".tmp", f"call_{self.calls}.py")
        with open(script, "w") as f:
            f.write(code or "")
        cmd = [sys.executable, "-I", script]
        if self.mode == "sandbox-exec":
            cmd = [SANDBOX_EXEC, "-p", _PROFILE.format(ws=self.dir)] + cmd
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=self.dir, env=self._env(), capture_output=True, text=True, timeout=timeout,
                               errors="replace")
            out, code_ = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else ""), p.returncode
        except subprocess.TimeoutExpired as e:
            out = ((e.stdout or "") if isinstance(e.stdout, str) else "") + f"\n[stopped: over {timeout} s]"
            code_ = "timeout"
        if len(out) > MAX_OUT:
            out = out[:MAX_OUT // 2] + f"\n[... {len(out) - MAX_OUT} characters cut ...]\n" + out[-MAX_OUT // 2:]
        result = f"exit code {code_}\n{out}" if out.strip() else f"exit code {code_} (no output)"
        if self.log:
            self.log({"kind": "tool", "tool": TOOL_NAME, "call": self.calls, "seconds": round(time.time() - t0, 2),
                      "code": code, "result": result})
        return result

    def tool(self, name, args):
        """Executor for the tool loops: handles run_python, returns None for any other tool."""
        if name != TOOL_NAME:
            return None
        return self.run(str((args or {}).get("code", "")))


def self_test():
    """Check this machine before a paid run: code runs, files are there by name, network and outside writes fail."""
    probe = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    probe.write("a,b\n1,2\n")
    probe.close()
    outside = os.path.join(os.path.expanduser("~"), "eeh_sandbox_probe.txt")
    ok = True
    try:
        with Workspace([probe.name]) as ws:
            print("isolation:", ws.mode)
            checks = [
                ("runs code", "print(6*7)", lambda r: "42" in r),
                ("reads a task file by name", f"print(open('{os.path.basename(probe.name)}').read())", lambda r: "a,b" in r),
                ("writes in its own folder", "open('out.txt','w').write('x'); print('ok')", lambda r: "ok" in r),
                ("network is blocked", "import socket\ntry:\n    socket.create_connection(('example.com', 80), timeout=5); print('NETWORK OPEN')\n"
                                       "except Exception as e:\n    print('blocked', type(e).__name__)", lambda r: "blocked" in r),
                ("writes outside are blocked", f"try:\n    open({outside!r},'w').write('x'); print('WROTE OUTSIDE')\n"
                                               "except Exception as e:\n    print('blocked', type(e).__name__)", lambda r: "blocked" in r),
                ("no API keys in its environment", "import os; print([k for k in os.environ if 'KEY' in k or 'PROJECT' in k])",
                 lambda r: "[]" in r),
            ]
            for name, code, good in checks:
                r = ws.run(code, timeout=30)
                passed = good(r)
                ok &= passed
                print(f"  {'OK  ' if passed else 'FAIL'} {name}: {' '.join(r.split())[:120]}")
            r = ws.run("import importlib.util as u; print({m: bool(u.find_spec(m)) for m in ['numpy','pandas','scipy','matplotlib']})")
            print("  libraries:", " ".join(r.split()[3:]))
    finally:
        os.unlink(probe.name)
        if os.path.exists(outside):
            os.unlink(outside)
    print("sandbox ready" if ok else "sandbox NOT ready: do not run with --sandbox local")
    return ok


if __name__ == "__main__":
    sys.exit(0 if self_test() else 1)
