<#
  Désinstalle BepInEx (et le plugin ClubDirector) de FM26 : met à la Corbeille les éléments ajoutés
  à l'installation (liste dans %LOCALAPPDATA%\ClubDirectorAI\bepinex-install.json). Les fichiers du jeu
  ne sont jamais touchés. Fermer FM26 avant.
  Usage : powershell -ExecutionPolicy Bypass -File scripts\uninstall_bepinex.ps1
#>
$ErrorActionPreference = "Stop"
$manifest = Join-Path $env:LOCALAPPDATA "ClubDirectorAI\bepinex-install.json"
if (-not (Test-Path $manifest)) { throw "Manifeste introuvable : $manifest" }
$m = Get-Content $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
if (Get-Process fm -ErrorAction SilentlyContinue) { throw "FM26 est lancé : fermez le jeu d'abord." }
Add-Type -AssemblyName Microsoft.VisualBasic
foreach ($name in $m.top_level_items) {
  $path = Join-Path $m.game_dir $name
  if (-not (Test-Path $path)) { continue }
  if ((Get-Item $path -Force).PSIsContainer) {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($path, "OnlyErrorDialogs", "SendToRecycleBin")
  } else {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($path, "OnlyErrorDialogs", "SendToRecycleBin")
  }
  Write-Host "Corbeille : $path"
}
Write-Host "BepInEx retiré de FM26 (récupérable depuis la Corbeille)."
