$ErrorActionPreference = "Stop"

function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Find-Pythonw($pythonPath) {
    if (-not $pythonPath) {
        return $null
    }

    $pythonw = Join-Path (Split-Path -Parent $pythonPath) "pythonw.exe"
    if (Test-Path -LiteralPath $pythonw) {
        return $pythonw
    }

    return $pythonPath
}

function Write-Launcher($installDir, $pythonwPath) {
    $launcherPath = Join-Path $installDir "abrir_interface.vbs"
    $content = @"
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = "$pythonwPath"
command = """" & pythonw & """ -m automacao_correcao.gui"
shell.CurrentDirectory = base
shell.Run command, 0, False
"@
    Set-Content -LiteralPath $launcherPath -Value $content -Encoding ASCII
    return $launcherPath
}

function Create-Shortcut($shortcutPath, $targetPath, $workingDirectory, $iconPath) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.IconLocation = $iconPath
    $shortcut.Description = "Automações MSB"
    $shortcut.Save()
}

$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installDir = Join-Path $env:LOCALAPPDATA "AutomacoesMSB"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Automações MSB.lnk"

Write-Host ""
Write-Host "Instalando Automações MSB..." -ForegroundColor Cyan

$python = Find-Python
if (-not $python) {
    Write-Host ""
    Write-Host "Python nao encontrado." -ForegroundColor Red
    Write-Host "Instale o Python 3.10 ou superior e marque a opcao 'Add Python to PATH'."
    Write-Host "Depois execute este instalador novamente."
    exit 1
}

$pythonw = Find-Pythonw $python

Write-Host "Python encontrado: $python"
Write-Host "Pasta de instalacao: $installDir"

New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceDir "automacao_correcao") -Destination $installDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "requirements.txt") -Destination $installDir -Force

Write-Host ""
Write-Host "Instalando dependencias..." -ForegroundColor Cyan
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $installDir "requirements.txt")

Write-Host ""
Write-Host "Criando atalho..." -ForegroundColor Cyan
$launcher = Write-Launcher $installDir $pythonw
$icon = Join-Path $installDir "automacao_correcao\assets\msb_icon.ico"
Create-Shortcut $desktopShortcut $launcher $installDir $icon

Write-Host ""
Write-Host "Instalacao concluida!" -ForegroundColor Green
Write-Host "Atalho criado em: $desktopShortcut"
Write-Host "Agora basta abrir 'Automações MSB' pela Area de Trabalho."
