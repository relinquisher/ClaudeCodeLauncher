"""PTYテスト：echo コマンドを実行して出力を読む"""
import sys
sys.path.insert(0, r"C:\Users\Y\Documents\ClaudeCodeLauncher")
from read_Japanese import log
from winpty import PtyProcess
import time

try:
    log("[TEST] PtyProcess で echo テスト開始")
    pty = PtyProcess.spawn(["cmd", "/c", "echo", "日本語テスト"])
    log(f"[TEST] PTY起動成功, isalive={pty.isalive()}")

    # データを読む
    for i in range(10):
        try:
            data = pty.read(4096)
            if data:
                log(f"[TEST] データ受信 ({i}回目): {len(data)}bytes - {repr(data[:50])}")
            else:
                log(f"[TEST] データなし ({i}回目), isalive={pty.isalive()}")
                if not pty.isalive():
                    log("[TEST] PTY終了")
                    break
        except EOFError:
            log(f"[TEST] EOF ({i}回目)")
            break
        except Exception as e:
            log(f"[TEST] エラー ({i}回目): {type(e).__name__}: {e}")
            break
        time.sleep(0.1)

    pty.close(force=True)
    log("[TEST] 完了")

    # ログ表示
    print("\n=== ログ内容 ===")
    import os
    debug_file = os.path.expanduser("~/.claude_tts_debug.log")
    with open(debug_file, 'r', encoding='utf-8') as f:
        print(f.read())

except Exception as e:
    log(f"[TEST] 例外: {e}")
    import traceback
    log(traceback.format_exc())
    print(traceback.format_exc())
