"""claude を疑似端末(PTY)経由で起動し、画面表示はそのまま中継しつつ
コードブロック外の日本語だけを読み上げるラッパー。

claude はインタラクティブ REPL で、標準出力が通常のパイプ/リダイレクトだと
TTY と認識できず "--print" 相当の非対話モード扱いになってエラー終了する。
そのため PTY (winpty) を使い、claude からは通常のターミナルに見えるようにする。

使い方: read_Japanese.py <実行するコマンドとその引数...>
  例) read_Japanese.py claude --model haiku --dangerously-skip-permissions
"""
import sys
import re
import os
import subprocess
import threading

try:
    import msvcrt
except ImportError:
    msvcrt = None

from winpty import PtyProcess

# ひらがな、カタカナ、漢字を含む正規表現
JA_RE = re.compile(r'[぀-ゟ゠-ヿ一-鿿]')
# ANSI エスケープシーケンス（カーソル移動・色付けなど）
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07')

# 直近読み上げたテキストの履歴（TUI の再描画による重複読み上げを防ぐ）
_spoken_history = []
_HISTORY_MAX = 30

# 拡張キー（矢印キーなど）→ ANSI エスケープシーケンス
ARROW_MAP = {
    'H': '\x1b[A',   # Up
    'P': '\x1b[B',   # Down
    'K': '\x1b[D',   # Left
    'M': '\x1b[C',   # Right
    'G': '\x1b[H',   # Home
    'O': '\x1b[F',   # End
    'S': '\x1b[3~',  # Delete
}


def speak(text):
    try:
        safe_text = text.replace('"', '""').replace("'", "''")
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$synth.Speak('{safe_text}')"
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def maybe_speak(clean_text, in_code_block):
    text = clean_text.strip()
    if not text or in_code_block:
        return
    if not JA_RE.search(text):
        return
    if text in _spoken_history:
        return
    _spoken_history.append(text)
    if len(_spoken_history) > _HISTORY_MAX:
        _spoken_history.pop(0)
    speak(text)


def stdin_forwarder(pty):
    """標準入力のキー入力を読み取り、PTY へ転送するスレッド"""
    if msvcrt is None:
        return
    while True:
        try:
            ch = msvcrt.getwch()
        except Exception:
            break
        try:
            if ch in ('\x00', '\xe0'):
                # 拡張キー（矢印キーなど）
                ch2 = msvcrt.getwch()
                seq = ARROW_MAP.get(ch2)
                if seq:
                    pty.write(seq)
                continue
            pty.write(ch)
        except Exception:
            break


def main():
    if len(sys.argv) < 2:
        print("使い方: read_Japanese.py <実行するコマンド...>", file=sys.stderr)
        sys.exit(1)

    argv = sys.argv[1:]

    try:
        size = os.get_terminal_size()
        cols, rows = size.columns, size.lines
    except Exception:
        cols, rows = 120, 30

    try:
        pty = PtyProcess.spawn(argv, dimensions=(rows, cols))
    except Exception as e:
        print(f"起動に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    t = threading.Thread(target=stdin_forwarder, args=(pty,), daemon=True)
    t.start()

    in_code_block = False
    line_buf = ""

    try:
        while True:
            try:
                data = pty.read(4096)
            except EOFError:
                break
            except Exception:
                break
            if not data:
                if not pty.isalive():
                    break
                continue

            sys.stdout.write(data)
            sys.stdout.flush()

            line_buf += data
            while True:
                idx = line_buf.find('\n')
                if idx == -1:
                    break
                raw_line = line_buf[:idx]
                line_buf = line_buf[idx + 1:]
                clean = ANSI_RE.sub('', raw_line).strip('\r').strip()
                if clean.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                maybe_speak(clean, in_code_block)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pty.close(force=True)
        except Exception:
            pass

    print("\n[セッションが終了しました。何かキーを押すと閉じます...]")
    try:
        if msvcrt is not None:
            msvcrt.getwch()
    except Exception:
        pass


if __name__ == "__main__":
    main()
