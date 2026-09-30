"""claude を疑似端末(PTY)経由で起動し、画面表示はそのまま中継しつつ
「●」で始まる日本語行のみを読み上げるラッパー。
"""
import sys
import re
import os
import subprocess
import threading
import datetime
import time
import signal
import shutil

try:
    import msvcrt
except ImportError:
    msvcrt = None

from winpty import PtyProcess

# ひらがな、カタカナ、漢字を含む正規表現
JA_RE = re.compile(r'[぀-ゟ゠-ヿ一-鿿]')
# ANSI エスケープシーケンス
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[>7890]')

_spoken_history = set()  # 読み上げ済みのハッシュセット
DEBUG_FILE = os.path.expanduser("~/.claude_tts_debug.log")
_tts_lock = threading.Lock()
_tts_in_progress = False

ARROW_MAP = {
    'H': '\x1b[A', 'P': '\x1b[B', 'K': '\x1b[D', 'M': '\x1b[C',
    'G': '\x1b[H', 'O': '\x1b[F', 'S': '\x1b[3~',
}


def log(msg):
    """デバッグログをファイルに記録"""
    try:
        with open(DEBUG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def _speak_sync(text):
    """バックグラウンドで日本語テキストを読み上げる"""
    global _tts_in_progress

    def tts_worker():
        global _tts_in_progress
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(text)
                temp_file = f.name

            log(f"[TTS] 読み上げ開始: {text[:50]}")

            try:
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Speech; "
                    f"$text = Get-Content -Path '{temp_file}' -Raw -Encoding UTF8; "
                    f"$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$speak.Rate = 2; "
                    f"$speak.Speak($text)"
                )
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                proc.wait(timeout=15)
                log(f"[TTS] 読み上げ完了")
            finally:
                time.sleep(0.2)
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
        except Exception as e:
            log(f"[TTS] エラー: {e}")
        finally:
            _tts_in_progress = False

    with _tts_lock:
        if _tts_in_progress:
            return
        _tts_in_progress = True

    # バックグラウンドスレッドで実行（メインスレッドをブロックしない）
    t = threading.Thread(target=tts_worker, daemon=True)
    t.start()


def speak(text):
    """テキストを読み上げ（バックグラウンド処理、重複チェック付き）"""
    text_hash = hash(text)

    with _tts_lock:
        if text_hash in _spoken_history:
            log(f"[SKIP] 重複: {text[:50]}")
            return
        _spoken_history.add(text_hash)

    # ロック外で TTS 実行（ブロッキングなし）
    _speak_sync(text)


def maybe_speak(clean_text, in_code_block):
    """テキストを読み上げ対象として判定 - 「●」で始まる行のみ"""
    text = clean_text.strip()
    if not text or in_code_block:
        return

    # 「●」で始まる行のみを読み上げ対象
    if not text.startswith("●"):
        return

    # 「●」を除去してクリーンアップ
    filtered = text[1:].strip()

    # ANSI エスケープシーケンスが残っていたら除外
    if '\x1b' in filtered:
        log(f"[SKIP] ANSIコード含む: {filtered[:50]}")
        return

    # 制御文字（ord < 32、改行・タブ除く）を除外
    if any(ord(c) < 32 and c not in '\t\n\r' for c in filtered):
        log(f"[SKIP] 制御コード含む: {filtered[:50]}")
        return

    # 日本語を含まない行はスキップ
    if not JA_RE.search(filtered):
        return

    # ツール呼び出し行（例: Write(E:\path\対策.md), Bash(...), xxx (MCP)(...)）はスキップ
    if re.match(r'^[A-Za-z][\w.:\- ]*(\(MCP\))?\(', filtered):
        log(f"[SKIP] ツール呼び出し: {filtered[:50]}")
        return

    # 最初の単語がコマンド名（英数字のみ）の場合はスキップ
    first_word = filtered.split()[0] if filtered.split() else ""
    if first_word and re.match(r'^[a-zA-Z0-9._\-]+$', first_word):
        log(f"[SKIP] コマンド名のみ: {first_word}")
        return

    log(f"[読み上げ] {filtered[:80]}")
    speak(filtered)


_saved_modes = []


def _setup_console():
    """入力を VT モード(生バイト中継)、出力を VT 処理有効にする。終了時に復元する。"""
    import ctypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetStdHandle.restype = ctypes.c_void_p
    k32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    k32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    hin = k32.GetStdHandle(-10)
    hout = k32.GetStdHandle(-11)

    m = ctypes.c_ulong()
    if k32.GetConsoleMode(hin, ctypes.byref(m)):
        _saved_modes.append((k32, hin, m.value))
        # LINE_INPUT/ECHO/PROCESSED を切り、VIRTUAL_TERMINAL_INPUT を入れる
        new_in = (m.value & ~(0x0001 | 0x0002 | 0x0004)) | 0x0200
        ok = k32.SetConsoleMode(hin, new_in)
        log(f"[CONSOLE] stdin mode {m.value:#x} -> {new_in:#x} ok={bool(ok)}")
    if k32.GetConsoleMode(hout, ctypes.byref(m)):
        _saved_modes.append((k32, hout, m.value))
        new_out = m.value | 0x0001 | 0x0004  # PROCESSED_OUTPUT | VT_PROCESSING
        ok = k32.SetConsoleMode(hout, new_out)
        log(f"[CONSOLE] stdout mode {m.value:#x} -> {new_out:#x} ok={bool(ok)}")
    return k32, hin


def _restore_console():
    for k32, h, v in _saved_modes:
        try:
            k32.SetConsoleMode(h, v)
        except Exception:
            pass


def stdin_forwarder(pty, k32, hin):
    """端末からの入力(キー・マウス・DA応答などのVTシーケンス)を生バイトのまま PTY へ中継"""
    import ctypes
    import codecs
    k32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                             ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
    dec = codecs.getincrementaldecoder('utf-8')(errors='replace')
    buf = ctypes.create_string_buffer(4096)
    n = ctypes.c_ulong()
    while True:
        if not k32.ReadFile(hin, buf, 4096, ctypes.byref(n), None) or n.value == 0:
            log(f"[INPUT] ReadFile 終了 err={ctypes.get_last_error()}")
            break
        text = dec.decode(buf.raw[:n.value])
        if not text:
            continue
        try:
            pty.write(text)
        except Exception as e:
            log(f"[INPUT] PTY書き込み失敗: {e}")
            break


def window_size_monitor(pty, stop_event):
    """端末サイズの変更を監視して PTY に反映する"""
    last = shutil.get_terminal_size((120, 30))
    while not stop_event.wait(0.1):
        try:
            cur = shutil.get_terminal_size((120, 30))
            if cur != last:
                log(f"[RESIZE] {last.columns}x{last.lines} -> {cur.columns}x{cur.lines}")
                pty.setwinsize(cur.lines, cur.columns)
                last = cur
        except Exception as e:
            log(f"[RESIZE] エラー: {e}")


def main():
    # ログクリア
    try:
        with open(DEBUG_FILE, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass

    log("=== read_Japanese.py 起動 ===")
    log(f"argv: {sys.argv}")

    if len(sys.argv) < 2:
        log("エラー: コマンドが指定されていません")
        sys.exit(1)

    argv = sys.argv[1:]
    log(f"実行コマンド: {argv}")

    try:
        cols, rows = shutil.get_terminal_size((120, 30))
    except Exception:
        cols, rows = 120, 30

    try:
        log(f"PtyProcess.spawn() 実行中... (rows={rows}, cols={cols})")
        pty = PtyProcess.spawn(argv, dimensions=(rows, cols))
        log("PtyProcess 起動成功")

        try:
            pty.setwinsize(rows, cols)
        except Exception:
            pass
    except Exception as e:
        log(f"PtyProcess 起動失敗: {e}")
        sys.exit(1)

    stop_event = threading.Event()

    try:
        k32, hin = _setup_console()
        threading.Thread(target=stdin_forwarder, args=(pty, k32, hin), daemon=True).start()
    except Exception as e:
        log(f"[CONSOLE] 設定失敗: {e}")
    threading.Thread(target=window_size_monitor, args=(pty, stop_event), daemon=True).start()

    in_code_block = False
    line_buf = ""
    line_count = 0

    try:
        log("メインループ開始")

        while True:
            try:
                data = pty.read(4096)
            except EOFError:
                log("EOFError")
                break
            except Exception as e:
                log(f"read エラー: {type(e).__name__}: {e}")
                break

            if not data:
                if not pty.isalive():
                    log("PTY終了")
                    break

                time.sleep(0.01)
                continue

            sys.stdout.write(data)
            sys.stdout.flush()

            line_buf += data

            # \r または \n で行を分割
            while True:
                idx_n = line_buf.find('\n')
                idx_r = line_buf.find('\r')

                if idx_n == -1 and idx_r == -1:
                    break

                # より早い方を使用
                if idx_n != -1 and (idx_r == -1 or idx_n < idx_r):
                    idx = idx_n
                    next_char = idx_n + 1
                else:
                    idx = idx_r
                    next_char = idx_r + 1
                    if next_char < len(line_buf) and line_buf[next_char] == '\n':
                        next_char += 1

                raw_line = line_buf[:idx]
                line_buf = line_buf[next_char:]

                # ANSIシーケンス削除
                clean = ANSI_RE.sub('', raw_line).strip()
                line_count += 1

                if clean.startswith("```"):
                    in_code_block = not in_code_block
                    log(f"[行{line_count}] コードブロック: {in_code_block}")
                    continue

                if clean:
                    maybe_speak(clean, in_code_block)

    except KeyboardInterrupt:
        log("KeyboardInterrupt")
    finally:
        stop_event.set()
        _restore_console()
        try:
            pty.close(force=True)
        except Exception:
            pass
        log("=== セッション終了 ===")

    print("\n[セッションが終了しました。何かキーを押すと閉じます...]")
    try:
        if msvcrt is not None:
            msvcrt.getwch()
    except Exception:
        pass


if __name__ == "__main__":
    main()
