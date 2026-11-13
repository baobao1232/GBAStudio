"""GBA Studio V12 launcher.

Keep the console attached while Python/PySide imports are being validated so
startup failures remain visible. Once imports succeed, detach the console on
Windows and run the GUI without a terminal window.
"""
import sys
import traceback

try:
    from gba_studio.app import run_app
except Exception:
    traceback.print_exc()
    try:
        input("\nKhông thể khởi động GBA Studio. Nhấn Enter để thoát...")
    except EOFError:
        pass
    sys.exit(1)

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass

run_app()
