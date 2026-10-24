"""Windows: there's no single "time spent waiting" number like Ubuntu's PSI,
so we combine two signals that come close:

- hard faults/s: how often programs had to fetch their memory back from disk
  because RAM was full. Read from the "\\Memory\\Pages Input/sec" counter.
- the window you're using: is it frozen? Windows marks a window "Not Responding"
  when it hasn't handled input for about 5 s (IsHungAppWindow).

Disk latency and the heartbeat probe work on both OSes, so they live in the collector.
Neither signal here needs admin rights. If anything fails we return None, never crash.
"""

import ctypes

import psutil

try:
    import win32pdh  # from the pywin32 package
except ImportError:
    win32pdh = None


class WindowsProbe:
    def __init__(self):
        self._query = None
        self._hard_faults = None
        if win32pdh is not None:
            try:
                self._query = win32pdh.OpenQuery()
                # "English" names work on any Windows language.
                self._hard_faults = win32pdh.AddEnglishCounter(self._query, r"\Memory\Pages Input/sec")
                # Rate counters need two readings; this first one primes it.
                win32pdh.CollectQueryData(self._query)
            except Exception:
                self._query = None

    def waiting_signals(self) -> dict:
        app, hung = self._foreground_window()
        return {
            "hard_faults_per_s": self._read_hard_faults(),
            "foreground_app": app,
            "foreground_hung": hung,
        }

    def temperature_c(self) -> float | None:
        # Most laptops hide temperatures from normal apps on Windows (decision 5).
        # Overheating is spotted from CPU speed drops instead.
        return None

    def _read_hard_faults(self) -> float | None:
        if self._query is None:
            return None
        try:
            win32pdh.CollectQueryData(self._query)
            _, value = win32pdh.GetFormattedCounterValue(self._hard_faults, win32pdh.PDH_FMT_DOUBLE)
            return float(value)
        except Exception:
            return None

    def _foreground_window(self) -> tuple[str | None, bool | None]:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None, None
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            hung = bool(user32.IsHungAppWindow(hwnd))
            return psutil.Process(pid.value).name(), hung
        except Exception:
            return None, None
