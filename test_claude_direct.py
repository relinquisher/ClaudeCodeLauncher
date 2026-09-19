"""Claude Code CLIを直接テスト"""
import subprocess
import sys

print("=== Claude CLIのテスト（通常モード） ===")
try:
    # 通常のsubprocess.Popen で Claude を起動（パイプで出力をキャプチャ）
    proc = subprocess.Popen(
        ["claude", "--model", "haiku", "--print", "こんにちは"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )

    stdout, stderr = proc.communicate(timeout=10)

    print(f"戻り値: {proc.returncode}")
    print(f"\n=== STDOUT ===")
    print(stdout[:500] if stdout else "(なし)")
    print(f"\n=== STDERR ===")
    print(stderr[:500] if stderr else "(なし)")

except Exception as e:
    print(f"エラー: {e}")

print("\n=== Claude CLIのテスト（PTY経由） ===")
try:
    from winpty import PtyProcess
    import time

    pty = PtyProcess.spawn(["claude", "--model", "haiku", "--dangerously-skip-permissions"])
    print(f"PTY起動成功: isalive={pty.isalive()}")

    # 最初の出力を待つ
    data_received = []
    for i in range(10):
        try:
            data = pty.read(4096)
            if data:
                data_received.append((i, len(data), repr(data[:50])))
                print(f"[{i}] データ: {len(data)}bytes - {repr(data[:50])}")
            else:
                print(f"[{i}] データなし (isalive={pty.isalive()})")
        except EOFError:
            print(f"[{i}] EOF")
            break
        except Exception as e:
            print(f"[{i}] エラー: {e}")
            break
        time.sleep(0.5)

    pty.close(force=True)
    print(f"\nデータ受信: {len(data_received)}回")

except Exception as e:
    print(f"エラー: {e}")
    import traceback
    traceback.print_exc()
