"""Claude CLIのデータをダンプ"""
from winpty import PtyProcess
import time

pty = PtyProcess.spawn(["claude", "--model", "haiku", "--dangerously-skip-permissions"])
print("PTY起動")

all_data = []
for i in range(20):
    try:
        data = pty.read(4096)
        if data:
            all_data.append(data)
            print(f"[{i}] {len(data)}bytes")
        else:
            print(f"[{i}] (なし)")
    except EOFError:
        print(f"[{i}] EOF")
        break
    except Exception as e:
        print(f"[{i}] エラー: {e}")
        break
    time.sleep(0.3)

pty.close(force=True)

# 全データを表示
print("\n=== 全受信データ（raw） ===")
combined = b''.join(all_data)
print(repr(combined[:500]))

print("\n=== 全受信データ（改行あり） ===")
print(combined.decode('utf-8', errors='replace'))

print("\n=== データ統計 ===")
print(f"パケット数: {len(all_data)}")
print(f"合計バイト数: {len(combined)}")
newline_count = combined.count(b'\n')
print(f"改行数: {newline_count}")
prompt_bytes = '❯'.encode('utf-8')
has_prompt = prompt_bytes in combined
print(f"日本語「❯」含む: {has_prompt}")
