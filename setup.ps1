# Первоначальная настройка: окружение Python, зависимости, сборка интерфейса.
# Запуск:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Fail($text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; exit 1 }
function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

Step 'Проверка Python и Node.js'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Fail 'Python не найден. Установите Python 3.11+ с python.org (отметьте "Add python.exe to PATH").' }
$pyVersion = [version]((& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim())
if ($pyVersion -lt [version]'3.11') { Fail "Нужен Python 3.11 или новее, найден $pyVersion." }
Write-Host "Python $pyVersion"

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { Fail 'Node.js не найден. Установите Node.js 20+ (LTS) с nodejs.org.' }
$nodeVersion = [version]((& node --version).Trim().TrimStart('v'))
if ($nodeVersion.Major -lt 20) { Fail "Нужен Node.js 20 или новее, найден $nodeVersion." }
Write-Host "Node.js $nodeVersion"

Step 'Виртуальное окружение Python (backend\.venv)'
$venvPython = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    & python -m venv (Join-Path $root 'backend\.venv')
    if ($LASTEXITCODE -ne 0) { Fail 'Не удалось создать виртуальное окружение.' }
}
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $root 'backend\requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { Fail 'Не удалось установить Python-зависимости (нужен интернет при первой установке).' }

Step 'Зависимости и сборка интерфейса (frontend)'
Push-Location (Join-Path $root 'frontend')
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { Fail 'npm ci завершился с ошибкой.' }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Fail 'Сборка интерфейса не удалась.' }
} finally { Pop-Location }

Step 'Готово'
Write-Host 'Запускайте приложение командой:  .\start.ps1' -ForegroundColor Green
