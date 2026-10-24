"""Start the collector automatically when you log in.

    python -m whyslow install     start now, and at every login
    python -m whyslow uninstall   stop starting at login

Windows: a tiny script in your Startup folder runs the collector with
pythonw.exe, which has no console window, so nothing pops up.
Ubuntu: a systemd "user service", which also restarts it if it ever crashes.
Neither needs admin rights.
"""

import os
import subprocess
import sys
from pathlib import Path

NAME = "whyslow"


def _pythonw() -> str:
    """The windowless Python next to the one running us (inside .venv)."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def _windows_startup_file() -> Path:
    startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / f"{NAME}.vbs"


def _linux_service_file() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{NAME}.service"


def install() -> str:
    if sys.platform == "win32":
        pythonw = _pythonw()
        script = _windows_startup_file()
        # 0 = hidden window, False = don't wait for it to finish.
        script.write_text(
            'Set shell = CreateObject("WScript.Shell")\r\n'
            f'shell.Run """{pythonw}"" -m {NAME} collect", 0, False\r\n'
        )
        subprocess.Popen([pythonw, "-m", NAME, "collect"], creationflags=subprocess.DETACHED_PROCESS)
        return f"Collector started, and will start at every login.\nStartup script: {script}"

    if sys.platform.startswith("linux"):
        service = _linux_service_file()
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text(
            "[Unit]\n"
            "Description=whyslow collector: records why your laptop is slow\n\n"
            "[Service]\n"
            f"ExecStart={sys.executable} -m {NAME} collect\n"
            "Restart=on-failure\n"
            "Nice=10\n\n"  # lower priority than your apps, so it never competes with them
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", NAME], check=True)
        return f"Collector started, and will start at every login.\nService file: {service}"

    return "Starting at login isn't supported on this OS yet. Run `python -m whyslow collect` yourself."


def uninstall() -> str:
    if sys.platform == "win32":
        _windows_startup_file().unlink(missing_ok=True)
        return "Won't start at login any more. A collector that's running now keeps going until you log out."
    if sys.platform.startswith("linux"):
        subprocess.run(["systemctl", "--user", "disable", "--now", NAME], check=False)
        _linux_service_file().unlink(missing_ok=True)
        return "Collector stopped, and won't start at login any more."
    return "Nothing to undo on this OS."
