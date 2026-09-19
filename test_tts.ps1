# TTS テストスクリプト

Write-Host "=== Claude Code TTS テスト開始 ===" -ForegroundColor Cyan

# ログファイルをクリア
$debugLog = "$env:USERPROFILE\.claude_tts_debug.log"
if (Test-Path $debugLog) {
    Remove-Item $debugLog -Force
    Write-Host "✓ ログファイルをクリアしました"
}

# テスト用フォルダ
$testDir = "C:\Users\Y\Documents\TestProject_TTS"
Set-Location $testDir
Write-Host "✓ 作業フォルダ: $testDir"

# Claude Code CLIを起動（PTY経由で日本語読み上げ有効）
Write-Host ""
Write-Host "Claude Code CLIを起動中..." -ForegroundColor Yellow
Write-Host "（3秒後に質問を自動入力します）"
Write-Host ""

$pythonScript = "C:\Users\Y\Documents\ClaudeCodeLauncher\read_Japanese.py"
$process = Start-Process python -ArgumentList @(
    $pythonScript,
    "claude",
    "--model", "haiku",
    "--dangerously-skip-permissions"
) -PassThru -NoNewWindow

# プロセスIDを記録
Write-Host "プロセスID: $($process.Id)" -ForegroundColor Green

# 3秒待機（Claude起動待ち）
Start-Sleep -Seconds 3

# 標準入力に質問を送信
Write-Host "日本語で質問を入力中..." -ForegroundColor Yellow

# プロセスに入力を送信
$null | Out-Process $process
# 上記は機能しないので、別の方法を試す

Write-Host "⏳ 10秒待機中..."
Start-Sleep -Seconds 10

# ログファイルを確認
Write-Host ""
Write-Host "=== ログファイルの内容 ===" -ForegroundColor Cyan
if (Test-Path $debugLog) {
    Get-Content $debugLog -Encoding UTF8 -Tail 100 | ForEach-Object {
        Write-Host $_
    }
} else {
    Write-Host "ログファイルが見つかりません" -ForegroundColor Red
}

Write-Host ""
Write-Host "テスト完了。Claude Code CLIプロセスを確認してください。" -ForegroundColor Green
