"""De få Windows-kald HUD'en har brug for. Alt er no-op på andre systemer.

- Globale genvejstaster via RegisterHotKey: ingen tastatur-hook og intet
  'keyboard'-modul at installere. Windows sender kun de taster du har valgt.
- Vinduet gøres click-through, uden fokus og uden plads på proceslinjen.
- Forgrundsvinduets klasse/titel læses for at se om Fortnite har fokus.
  (Der åbnes aldrig et håndtag til spillets proces.)
"""
from __future__ import annotations

import ctypes
import os
import threading

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x1, 0x2, 0x10, 0x200
HWND_TOPMOST = -1
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000


# --------------------------------------------------------------------------- DPI og vindue

def enable_dpi_awareness() -> None:
    """Skarp tekst på 125/150 %-skærme. Skal kaldes før Tk startes."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system-aware
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def toplevel_hwnd(root) -> int | None:
    if not IS_WINDOWS:
        return None
    try:
        return int(root.wm_frame(), 16)      # Tk's ydre vindue
    except (ValueError, TypeError):
        return user32.GetParent(root.winfo_id()) or root.winfo_id()


def make_overlay(hwnd) -> bool:
    """Click-through, tager aldrig fokus, ikke på proceslinjen/Alt+Tab.

    Kræver at Tk allerede har gjort vinduet 'layered' (sker når -alpha < 1 er sat),
    ellers bliver vinduet usynligt.
    """
    if not (IS_WINDOWS and hwnd):
        return False
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    style &= ~WS_EX_APPWINDOW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    return True


def keep_on_top(hwnd) -> None:
    """Fortnite i 'vinduesbaseret fuldskærm' kan skubbe andre topmost-vinduer bagud."""
    if IS_WINDOWS and hwnd:
        user32.SetWindowPos(hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)


def foreground_window():
    return user32.GetForegroundWindow() if IS_WINDOWS else None


def set_foreground(hwnd) -> None:
    if IS_WINDOWS and hwnd:
        user32.SetForegroundWindow(hwnd)


def window_info(hwnd) -> tuple[str, str]:
    """(klassenavn, titel) for et vindue."""
    if not (IS_WINDOWS and hwnd):
        return "", ""
    cls = ctypes.create_unicode_buffer(256)
    title = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    user32.GetWindowTextW(hwnd, title, 256)
    return cls.value, title.value


def fortnite_has_focus() -> bool | None:
    """True/False på Windows, None hvis det ikke kan afgøres."""
    if not IS_WINDOWS:
        return None
    cls, title = window_info(foreground_window())
    return cls == "UnrealWindow" or "fortnite" in title.lower()


# --------------------------------------------------------------------------- genvejstaster

_VK = {f"F{i}": 0x6F + i for i in range(1, 25)}
_VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
_VK.update({str(d): 0x30 + d for d in range(10)})
_VK.update({f"NUM{d}": 0x60 + d for d in range(10)})
_VK.update({
    "NUM*": 0x6A, "NUM+": 0x6B, "NUM-": 0x6D, "NUM.": 0x6E, "NUM/": 0x6F,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23, "HOME": 0x24,
    "INSERT": 0x2D, "DELETE": 0x2E, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
})
_MODS = {"ALT": MOD_ALT, "CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL, "SHIFT": MOD_SHIFT, "WIN": MOD_WIN}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'ctrl+F8' -> (MOD_CONTROL, 0x77). Rejser ValueError ved ukendte taster."""
    parts = [p.strip().upper() for p in str(spec).replace(" ", "").split("+") if p.strip()]
    if spec.strip().upper().endswith("NUM+"):   # 'NUM+' indeholder selv et plus
        parts = [p for p in parts if p != "NUM"] + ["NUM+"]
    if not parts:
        raise ValueError("tom tast")
    *mods, key = parts
    if key not in _VK:
        raise ValueError(f"ukendt tast '{key}'")
    if key == "F12":
        raise ValueError("F12 er reserveret af Windows")
    m = 0
    for mod in mods:
        if mod not in _MODS:
            raise ValueError(f"ukendt modifier '{mod}'")
        m |= _MODS[mod]
    return m, _VK[key]


class Hotkeys(threading.Thread):
    """Registrerer genvejstaster og kalder on_key(navn) fra sin egen tråd.

    on_key skal være trådsikker (HUD'en lægger bare navnet i en kø).
    """
    daemon = True

    def __init__(self, bindings: dict[str, str], on_key):
        super().__init__(name="hotkeys")
        self.bindings = {k: v for k, v in bindings.items() if v and not k.startswith("_")}
        self.on_key = on_key
        self.failed: list[str] = []
        self.registered: dict[str, str] = {}
        self.ready = threading.Event()
        self._thread_id = None

    def start_and_wait(self, timeout: float = 2.0) -> None:
        if not IS_WINDOWS:
            self.failed.append("genvejstaster virker kun på Windows")
            self.ready.set()
            return
        self.start()
        self.ready.wait(timeout)

    def run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        ids = {}
        for i, (name, spec) in enumerate(self.bindings.items(), start=1):
            try:
                mods, vk = parse_hotkey(spec)
            except ValueError as e:
                self.failed.append(f"{spec}: {e}")
                continue
            if user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                ids[i] = name
                self.registered[name] = spec
            else:
                self.failed.append(f"{spec} er optaget af et andet program")
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                try:
                    self.on_key(ids[msg.wParam])
                except Exception:
                    pass
        for i in ids:
            user32.UnregisterHotKey(None, i)

    def stop(self) -> None:
        if IS_WINDOWS and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
