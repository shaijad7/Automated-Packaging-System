import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

found_windows = []
def enum_windows_callback(hwnd, lParam):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value
        if "SMART INVENTORY" in title or "python" in title.lower():
            # Get process ID
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            is_visible = user32.IsWindowVisible(hwnd)
            found_windows.append({"title": title, "hwnd": hwnd, "pid": pid.value, "visible": is_visible})
    return True

user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)

if not found_windows:
    print("No visible windows found.")
else:
    for w in found_windows:
        print(f"Found Window: '{w['title']}' (PID: {w['pid']}, HWND: {w['hwnd']})")
