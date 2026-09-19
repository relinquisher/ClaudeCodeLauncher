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

    # バックスラッシュなどの制御文字を明示的に除外
    if '\\' in filtered or '\x1b' in filtered:
        log(f"[SKIP] 制御文字含む: {filtered[:50]}")
        return

    # 制御文字（ord < 32）を除外
    if any(ord(c) < 32 for c in filtered):
        log(f"[SKIP] 制御コード含む: {filtered[:50]}")
        return

    # 日本語を含まない行はスキップ
    if not JA_RE.search(filtered):
        return

    log(f"[読み上げ] {filtered[:80]}")
    speak(filtered)


def stdin_forwarder(pty):
    """標準入力のキー入力を読み取り、PTY へ転送するスレッド"""
    if msvcrt is None:
        return

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # マウス入力と拡張キーを有効化
        mode.value |= 0x0010  # ENABLE_MOUSE_INPUT
        mode.value |= 0x0080  # ENABLE_EXTENDED_FLAGS
        kernel32.SetConsoleMode(handle, mode)
        log("[INPUT] コンソール: マウスと拡張キーを有効化")
    except Exception as e:
        log(f"[INPUT] モード設定失敗: {e}")

    while True:
        try:
            ch = msvcrt.getwch()
        except Exception:
            log("[INPUT] getwch() 終了")
            break
        try:
            if ch in ('\x00', '\xe0'):
                ch2 = msvcrt.getwch()
                seq = ARROW_MAP.get(ch2)
                if seq:
                    pty.write(seq)
                continue
            pty.write(ch)
        except Exception as e:
            log(f"[INPUT] PTY書き込み失敗: {e}")
            break


def window_size_monitor(pty, stop_event):
    """ウインドウサイズの変更を定期的に監視するスレッド"""
    try:
        last_rows, last_cols = shutil.get_terminal_size((120, 30))
    except Exception:
        last_rows, last_cols = 120, 30

    while not stop_event.is_set():
        try:
            time.sleep(0.2)  # 200ms ごとにチェック
            try:
                new_cols, new_rows = shutil.get_terminal_size((120, 30))
            except Exception:
                continue

            if new_rows != last_rows or new_cols != last_cols:
                try:
                    log(f"[RESIZE] {last_rows}x{last_cols} -> {new_rows}x{new_cols}")
                    pty.setwinsize(new_rows, new_cols)
                    last_rows, last_cols = new_rows, new_cols
                except Exception as e:
                    log(f"[RESIZE] setwinsize エラー: {e}")
        except Exception as e:
            log(f"[MONITOR] エラー: {e}")
            break


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

    t = threading.Thread(target=stdin_forwarder, args=(pty,), daemon=True)
    t.start()

    monitor_thread = threading.Thread(
        target=window_size_monitor, args=(pty, stop_event), daemon=True)
    monitor_thread.start()

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
