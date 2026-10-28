"""エクスプローラーへの登録（ビューアとエディタで共通）。現在のユーザーだけに書く（管理者権限は要らない）。

登録するもの:
  1. Markdown ファイル（.md / .markdown）を「プログラムから開く」の一覧に出す
  2. フォルダーを右クリックしたメニューに「…で開く」を出す（Directory\\shell）
  3. フォルダーを開いて、何もない場所を右クリックしたメニューにも、同じものを出す（Directory\\Background\\shell）

アプリは、起動時にフォルダーのパスを渡されると、そのフォルダーの一覧を開く。

注意: Windows 11 では、右クリックですぐ出る短いメニューには、このような登録は出ず、
「その他のオプションを表示」（Shift+右クリック、Shift+F10 でも可）を押した先の、従来のメニューに出る。

テストでは classes に別の場所を渡して、本物の登録に触れずに確かめる。
"""
import ctypes

REAL_CLASSES = r"Software\Classes"
EXTENSIONS = (".md", ".markdown")


def _root():
    import winreg
    return winreg.HKEY_CURRENT_USER


def _put(key, value, name=""):
    import winreg
    with winreg.CreateKey(_root(), key) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def delete_tree(sub):
    """キーを、子ごと消す。無ければ何もしない。"""
    import winreg
    try:
        with winreg.OpenKey(_root(), sub, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                delete_tree(rf"{sub}\{child}")
        winreg.DeleteKey(_root(), sub)
    except OSError:
        pass


def register(exe, prog_id, text, verb, classes=REAL_CLASSES):
    """exe を、ファイルの「プログラムから開く」と、フォルダーの右クリックに登録する。

    prog_id: ファイルの種類の名前（例: MarkdownViewer.File）
    text:    メニューに出す文言（例: Markdown ビューアで開く）
    verb:    フォルダーのメニューのキー名。アプリごとに変える（同じだと、片方がもう片方を上書きする）
    """
    import winreg
    icon = f'"{exe}",0'
    # ---- 1. ファイル
    _put(rf"{classes}\{prog_id}", "Markdown 文書")
    _put(rf"{classes}\{prog_id}\DefaultIcon", icon)
    _put(rf"{classes}\{prog_id}\shell\open", text)
    _put(rf"{classes}\{prog_id}\shell\open\command", f'"{exe}" "%1"')
    for ext in EXTENSIONS:
        with winreg.CreateKey(_root(), rf"{classes}\{ext}\OpenWithProgids") as k:
            winreg.SetValueEx(k, prog_id, 0, winreg.REG_NONE, b"")
    # ---- 2. フォルダーを右クリック（%1 = そのフォルダー）
    base = rf"{classes}\Directory\shell\{verb}"
    _put(base, text)
    _put(base, icon, "Icon")
    _put(rf"{base}\command", f'"{exe}" "%1"')
    # ---- 3. フォルダーの中の、何もない場所を右クリック（%V = 開いているフォルダー）
    base = rf"{classes}\Directory\Background\shell\{verb}"
    _put(base, text)
    _put(base, icon, "Icon")
    _put(rf"{base}\command", f'"{exe}" "%V"')


def unregister(prog_id, verb, classes=REAL_CLASSES):
    """register が書いたものだけを消す（ほかのアプリの登録は残す）。"""
    import winreg
    delete_tree(rf"{classes}\{prog_id}")
    for ext in EXTENSIONS:
        try:
            with winreg.OpenKey(_root(), rf"{classes}\{ext}\OpenWithProgids", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, prog_id)
        except OSError:
            pass
    delete_tree(rf"{classes}\Directory\shell\{verb}")
    delete_tree(rf"{classes}\Directory\Background\shell\{verb}")


def notify_shell():
    """エクスプローラーに、登録が変わったことを知らせる（SHCNE_ASSOCCHANGED）。"""
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def clean_path_arg(arg):
    """起動引数のパスを整える。

    ルート（F:\\）を `"%V"` で渡されると、最後の `\\"` が引用符の印と解釈され、`F:"` という
    引数になる（Windows のコマンドラインの規則）。引用符が末尾に残っていたら、`\\` に戻す。
    """
    if arg and arg.endswith('"'):
        return arg[:-1] + "\\"
    return arg
