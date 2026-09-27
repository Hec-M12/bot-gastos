# Deja el bot prendido en Windows: arranca solo cuando inicias sesion (sin ventana negra).
#
# Como correrlo (en PowerShell, dentro de la carpeta del bot):
#   powershell -ExecutionPolicy Bypass -File servicio\windows\instalar.ps1
#   powershell -ExecutionPolicy Bypass -File servicio\windows\instalar.ps1 -Quitar
#
# Primero intenta con el Programador de tareas. Si Windows no deja (sin permisos),
# usa la carpeta "Inicio" como plan B. La compu tiene que estar prendida.
# (Este archivo va sin tildes a proposito: PowerShell viejo las lee mal.)
param([switch]$Quitar)
$ErrorActionPreference = "Stop"

$Carpeta = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Bot = Join-Path $Carpeta "bot.py"
$Tarea = "BotGastos"
$Atajo = Join-Path ([Environment]::GetFolderPath("Startup")) "BotGastos.lnk"

if ($Quitar) {
    try { Stop-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue } catch {}
    try { Unregister-ScheduledTask -TaskName $Tarea -Confirm:$false -ErrorAction SilentlyContinue } catch {}
    if (Test-Path $Atajo) { Remove-Item $Atajo }
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*bot.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Host "Listo: el bot ya no arranca solo. Tus datos siguen en $Carpeta\datos"
    exit 0
}

$ArchivoEnv = Join-Path $Carpeta ".env"
if (-not ((Test-Path $ArchivoEnv) -and (Select-String -Path $ArchivoEnv -Pattern '^TELEGRAM_TOKEN=["'']?[0-9]+:' -Quiet))) {
    Write-Host "No encuentro tu TELEGRAM_TOKEN en el archivo .env. Primero corre: py configurar.py telegram"
    exit 1
}

# Buscar pythonw.exe (Python sin ventana) a partir del Python instalado
$Exe = $null
foreach ($cand in @("py", "python", "python3")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $extra = @()
    if ($cand -eq "py") { $extra = @("-3") }
    try {
        $ruta = & $cmd.Source @extra -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2>$null
    } catch { $ruta = $null }
    if ($ruta -and (Test-Path $ruta)) { $Exe = $ruta; break }
}
if (-not $Exe) {
    Write-Host "No encuentro Python. Instalalo desde python.org (marca 'Add python.exe to PATH') y volve a correr esto."
    exit 1
}

New-Item -ItemType Directory -Force -Path (Join-Path $Carpeta "datos") | Out-Null
$ArgBot = "`"$Bot`""

try {
    $Accion = New-ScheduledTaskAction -Execute $Exe -Argument $ArgBot -WorkingDirectory $Carpeta
    $Disparador = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $Ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
    Register-ScheduledTask -TaskName $Tarea -Action $Accion -Trigger $Disparador -Settings $Ajustes `
        -Description "Bot de gastos por Telegram" -Force | Out-Null
    Start-ScheduledTask -TaskName $Tarea
    Write-Host "Listo (Programador de tareas): el bot quedo prendido y arranca solo cuando inicias sesion."
} catch {
    Write-Host "El Programador de tareas no me dejo ($($_.Exception.Message)). Uso la carpeta Inicio."
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($Atajo)
    $s.TargetPath = $Exe
    $s.Arguments = $ArgBot
    $s.WorkingDirectory = $Carpeta
    $s.Save()
    Start-Process -FilePath $Exe -ArgumentList $ArgBot -WorkingDirectory $Carpeta
    Write-Host "Listo (carpeta Inicio): el bot quedo prendido y arranca solo cuando inicias sesion."
}
Write-Host "Probalo: mandale /hoy en Telegram. Si algo falla, mira $Carpeta\datos\bot.log"
Write-Host "Importante: cerra la otra ventana donde lo tenias prendido (si quedan dos, Telegram se queja)."
