"""Windows 標準のファイル／フォルダー選択ダイアログ（ctypes）。

pywebview の create_file_dialog は画面とは別のスレッドから呼ぶと固まるため、
JS から呼ばれるスレッドでも安全に開けるよう Win32 を直接呼ぶ。
"""
import ctypes
from ctypes import wintypes

comdlg32 = ctypes.windll.comdlg32
shell32 = ctypes.windll.shell32
ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32

OFN_FILEMUSTEXIST = 0x1000
OFN_PATHMUSTEXIST = 0x0800
OFN_EXPLORER = 0x80000
OFN_NOCHANGEDIR = 0x8


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE), ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR), ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD), ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR), ("lCustData", wintypes.LPARAM),
        ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", ctypes.c_void_p), ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


def pick_file(initial_dir=None):
    buf = ctypes.create_unicode_buffer(32768)
    filt = ctypes.create_unicode_buffer(
        "Markdown (*.md;*.markdown)\0*.md;*.markdown;*.mdown;*.mkd\0"
        "All files (*.*)\0*.*\0\0", 256)
    # create_unicode_buffer は \0 を含む文字列を切らないが、長さを明示して確実にする
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = user32.GetForegroundWindow()
    ofn.lpstrFilter = ctypes.cast(filt, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrInitialDir = initial_dir
    ofn.lpstrTitle = "Markdown ファイルを開く"
    ofn.Flags = (OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER
                 | OFN_NOCHANGEDIR)
    if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return buf.value
    return None


OFN_OVERWRITEPROMPT = 0x2


SAVE_KINDS = {
    "md": ("Markdown (*.md)", "*.md", "md", "名前を付けて保存"),
    "pdf": ("PDF (*.pdf)", "*.pdf", "pdf", "PDF として保存"),
}


def pick_save(initial_dir=None, filename="無題.md", kind="md"):
    """「名前を付けて保存」。既存ファイルを選ぶと上書きの確認が出る。"""
    label, pattern, ext, title = SAVE_KINDS[kind]
    buf = ctypes.create_unicode_buffer(filename, 32768)
    filt = ctypes.create_unicode_buffer(
        label + "\0" + pattern + "\0All files (*.*)\0*.*\0\0", 256)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = user32.GetForegroundWindow()
    ofn.lpstrFilter = ctypes.cast(filt, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrInitialDir = initial_dir
    ofn.lpstrTitle = title
    ofn.lpstrDefExt = ext
    ofn.Flags = (OFN_PATHMUSTEXIST | OFN_OVERWRITEPROMPT | OFN_EXPLORER
                 | OFN_NOCHANGEDIR)
    if comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
        return buf.value
    return None


BIF_RETURNONLYFSDIRS = 0x1
BIF_EDITBOX = 0x10
BIF_NEWDIALOGSTYLE = 0x40
BFFM_INITIALIZED = 1
BFFM_SETSELECTIONW = 0x467


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [
        ("hwndOwner", wintypes.HWND), ("pidlRoot", ctypes.c_void_p),
        ("pszDisplayName", wintypes.LPWSTR), ("lpszTitle", wintypes.LPCWSTR),
        ("ulFlags", wintypes.UINT), ("lpfn", ctypes.c_void_p),
        ("lParam", wintypes.LPARAM), ("iImage", ctypes.c_int),
    ]


_CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.UINT,
                               wintypes.LPARAM, wintypes.LPARAM)
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


def _pick_folder_legacy(initial_dir=None):
    # 新しい形式のダイアログは COM（STA）を要する。呼び出しごとのスレッドで初期化する
    ole32.OleInitialize(None)
    try:
        @_CALLBACK
        def on_event(hwnd, msg, lparam, data):
            if msg == BFFM_INITIALIZED and initial_dir:
                user32.SendMessageW(hwnd, BFFM_SETSELECTIONW, 1,
                                    ctypes.cast(ctypes.c_wchar_p(initial_dir),
                                                ctypes.c_void_p).value)
            return 0

        name = ctypes.create_unicode_buffer(260)
        bi = BROWSEINFOW()
        bi.hwndOwner = user32.GetForegroundWindow()
        bi.pszDisplayName = ctypes.cast(name, wintypes.LPWSTR)
        bi.lpszTitle = "Markdown ファイルのあるフォルダーを選んでください"
        bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_EDITBOX
        bi.lpfn = ctypes.cast(on_event, ctypes.c_void_p)
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None
        path = ctypes.create_unicode_buffer(32768)
        ok = shell32.SHGetPathFromIDListW(pidl, path)
        ole32.CoTaskMemFree(pidl)
        return path.value if ok else None
    finally:
        ole32.OleUninitialize()


# --- エクスプローラー形式のフォルダー選択（IFileOpenDialog） -------------------
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        import uuid
        super().__init__()
        ctypes.memmove(ctypes.byref(self), uuid.UUID(text).bytes_le, 16)


CLSID_FileOpenDialog = "DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7"
IID_IFileOpenDialog = "D57C7288-D4AD-4768-BE02-9D969532D960"
IID_IShellItem = "43826D1E-E718-42EE-BC55-A1E261C37BFE"
FOS_PICKFOLDERS = 0x20
FOS_FORCEFILESYSTEM = 0x40
FOS_PATHMUSTEXIST = 0x800
SIGDN_FILESYSPATH = 0x80058000
ERROR_CANCELLED = 0x800704C7

ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
ole32.CoCreateInstance.restype = ctypes.c_long
shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                                ctypes.POINTER(GUID),
                                                ctypes.POINTER(ctypes.c_void_p)]
shell32.SHCreateItemFromParsingName.restype = ctypes.c_long


def _com(obj, index, *argtypes):
    """COM オブジェクトの vtable[index] を呼ぶ関数にする。"""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])


def _release(obj):
    if obj:
        _com(obj, 2)(obj)


def pick_folder(initial_dir=None):
    ole32.OleInitialize(None)
    dialog = ctypes.c_void_p()
    item = ctypes.c_void_p()
    try:
        hr = ole32.CoCreateInstance(ctypes.byref(GUID(CLSID_FileOpenDialog)), None, 1,
                                    ctypes.byref(GUID(IID_IFileOpenDialog)),
                                    ctypes.byref(dialog))
        if hr != 0 or not dialog:
            return _pick_folder_legacy(initial_dir)       # 使えない環境では従来の形式
        options = wintypes.DWORD()
        _com(dialog, 10, ctypes.POINTER(wintypes.DWORD))(dialog, ctypes.byref(options))
        _com(dialog, 9, wintypes.DWORD)(
            dialog, options.value | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
        _com(dialog, 17, wintypes.LPCWSTR)(dialog, "Markdown ファイルのあるフォルダーを選んでください")
        if initial_dir:
            start = ctypes.c_void_p()
            if shell32.SHCreateItemFromParsingName(
                    initial_dir, None, ctypes.byref(GUID(IID_IShellItem)),
                    ctypes.byref(start)) == 0:
                _com(dialog, 12, ctypes.c_void_p)(dialog, start)     # SetFolder
                _release(start)
        hr = _com(dialog, 3, wintypes.HWND)(dialog, user32.GetForegroundWindow())  # Show
        if hr & 0xFFFFFFFF == ERROR_CANCELLED:
            return None
        if hr != 0:
            return _pick_folder_legacy(initial_dir)
        if _com(dialog, 20, ctypes.POINTER(ctypes.c_void_p))(dialog, ctypes.byref(item)) != 0:
            return None
        name = ctypes.c_void_p()
        if _com(item, 5, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(
                item, SIGDN_FILESYSPATH, ctypes.byref(name)) != 0:
            return None
        path = ctypes.wstring_at(name.value)
        ole32.CoTaskMemFree(name)
        return path
    finally:
        _release(item)
        _release(dialog)
        ole32.OleUninitialize()
