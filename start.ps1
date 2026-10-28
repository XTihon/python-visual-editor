# Запуск приложения одной командой:  .\start.ps1
#   -Dev        режим разработки (Vite с горячей перезагрузкой на порту 5173)
#   -NoBrowser  не открывать браузер автоматически
#   -Port N     порт сервера (по умолчанию 8742)
param(
    [switch]$Dev,
    [switch]$NoBrowser,
    [int]$Port = 8742
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Fail($text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; exit 1 }

$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { Fail 'Окружение не настроено. Сначала выполните: .\setup.ps1' }
if (-not $Dev -and -not (Test-Path (Join-Path $root 'frontend\dist\index.html'))) {
    Fail 'Интерфейс не собран. Выполните: .\setup.ps1'
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Fail "Порт $Port уже занят (возможно, приложение уже запущено). Закройте его или укажите другой: .\start.ps1 -Port 8800"
}

$env:VR_PORT = "$Port"
$url = "http://127.0.0.1:$Port"
if ($Dev) {
    $env:VR_DEV = '1'
    $url = 'http://127.0.0.1:5173'
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm run dev' -WorkingDirectory (Join-Path $root 'frontend')
}

if (-not $NoBrowser) {
    # Ждём, пока сервер ответит, и открываем браузер.
    Start-Job -ArgumentList $Port, $url -ScriptBlock {
        param($p, $target)
        for ($i = 0; $i -lt 60; $i++) {
            try { Invoke-WebRequest "http://127.0.0.1:$p/api/health" -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process $target; return } catch { Start-Sleep -Milliseconds 500 }
        }
    } | Out-Null
}

Write-Host "Визуальный редактор: $url   (остановить: Ctrl+C)" -ForegroundColor Green
Set-Location (Join-Path $root 'backend')
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
