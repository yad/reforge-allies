"""Console output for the latest pipeline execution."""
import os
import shutil
import sys
import threading
import traceback
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "Logs"
PIPELINE_ENV = "REFORGE_PIPELINE_LOGS"


def reset_logs():
    if LOG_DIR.is_symlink():
        LOG_DIR.unlink()
    elif LOG_DIR.exists():
        shutil.rmtree(LOG_DIR)
    LOG_DIR.mkdir()


class _Tee:
    def __init__(self, console, logfile, lock):
        self.console = console
        self.logfile = logfile
        self.lock = lock

    def write(self, text):
        with self.lock:
            self.console.write(text)
            self.logfile.write(text)
        return len(text)

    def flush(self):
        with self.lock:
            self.console.flush()
            self.logfile.flush()

    def __getattr__(self, name):
        return getattr(self.console, name)


def run_logged(main, script):
    pipeline = os.environ.get(PIPELINE_ENV) == "1"
    if not pipeline:
        reset_logs()
    if not LOG_DIR.is_dir():
        raise FileNotFoundError(f"Dossier de journaux absent : {LOG_DIR} ; relancer la pipeline")
    path = LOG_DIR / (Path(script).stem + ".log")
    with path.open("a" if pipeline else "w", encoding="utf-8", errors="backslashreplace", buffering=1) as logfile:
        print(f"\n=== {Path(script).name} ===", file=logfile)
        lock = threading.RLock()
        stdout, stderr = (_Tee(stream, logfile, lock) for stream in (sys.stdout, sys.stderr))

        def record_failure(exc_type, exc, tb):
            if isinstance(exc, SystemExit):
                if exc.code not in (None, 0):
                    if not isinstance(exc.code, int):
                        print(exc.code, file=logfile)
                    print(f"[exit] {exc.code if isinstance(exc.code, int) else 1}", file=logfile)
            elif exc_type is not None:
                traceback.print_exception(exc_type, exc, tb, file=logfile)

        with ExitStack() as stack:
            stack.push(record_failure)
            stack.callback(stdout.flush)
            stack.callback(stderr.flush)
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            return main()


if __name__ == "__main__":
    reset_logs()
    print(f"Logs : {LOG_DIR}")
