# Coloca (ou tira) o PControl para abrir sozinho quando você entra no Windows.
param([switch]$Remove)

$root = Split-Path -Parent $PSScriptRoot
$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "PControl.lnk"

if ($Remove) {
    Remove-Item $link -ErrorAction SilentlyContinue
    Write-Host "O PControl não abre mais junto com o Windows."
    return
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
# pythonw = sem janela preta; o log fica em pcontrol.log.
$shortcut.TargetPath = Join-Path $root ".venv\Scripts\pythonw.exe"
$shortcut.Arguments = '"' + (Join-Path $root "server.py") + '"'
$shortcut.WorkingDirectory = $root
$shortcut.Description = "PControl: controle o PC pelo celular"
$shortcut.Save()
Write-Host "O PControl vai abrir sozinho quando você entrar no Windows."
