<#
  Installe ClubDirector AI pour l'utilisateur courant (aucun droit administrateur, rien hors de son profil) :
  1. vérifie les prérequis : uv, .NET 8 (SDK) et le runtime WebView2 — rien n'est téléchargé d'office ;
  2. prépare le service (uv sync) et compile la fenêtre du téléphone (Release) ;
  3. crée le dossier de données %LOCALAPPDATA%\ClubDirectorAI et config.toml depuis l'exemple s'ils manquent ;
  4. crée le dossier « ClubDirector AI » du menu Démarrer (lancer / désinstaller) et, seulement avec
     -Demarrage, un raccourci dans le dossier Démarrage de Windows : le service et le téléphone se lancent
     à l'ouverture de session (fenêtre réduite « ClubDirector »).
  Tout ce qui est créé est noté dans install.json ; scripts\uninstall_windows.ps1 l'enlève.
  Les sauvegardes FM26 ne sont jamais touchées.

  Usage : powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 [-Demarrage] [-SansMenu] [-Simulation]
    -Demarrage        lancer ClubDirector à l'ouverture de session Windows
    -SansMenu         pas de dossier dans le menu Démarrer
    -SansPreparation  ne pas lancer uv sync ni la compilation (déjà faits)
    -Simulation       affiche ce qui serait fait, sans rien modifier
#>
param(
  [switch]$Demarrage, [switch]$SansMenu, [switch]$SansPreparation, [switch]$Simulation,
  # Dossiers substituables (tests) : par défaut ceux de l'utilisateur courant.
  [string]$DossierDonnees = (Join-Path $env:LOCALAPPDATA "ClubDirectorAI"),
  [string]$DossierMenu = (Join-Path ([Environment]::GetFolderPath("Programs")) "ClubDirector AI"),
  [string]$DossierDemarrage = [Environment]::GetFolderPath("Startup")
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$overlayProj = Join-Path $root "overlay\ClubDirector.Overlay"
$overlayExe = Join-Path $overlayProj "bin\Release\net8.0-windows\ClubDirector.Overlay.exe"
$created = New-Object System.Collections.ArrayList

function Step([string]$text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Act([string]$text, [scriptblock]$action) {
  if ($Simulation) { Write-Host "  [simulation] $text" } else { Write-Host "  $text"; & $action }
}

function New-Shortcut([string]$path, [string]$script, [string]$arguments, [string]$description, [switch]$Visible) {
  Act "raccourci : $path" {
    $dir = Split-Path $path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $style = if ($Visible) { "" } else { "-WindowStyle Minimized " }
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass $style-File `"$script`" $arguments".Trim()
    $lnk.WorkingDirectory = $root
    $lnk.Description = $description
    $lnk.WindowStyle = if ($Visible) { 1 } else { 7 }  # 7 : réduite
    if (Test-Path $overlayExe) { $lnk.IconLocation = "$overlayExe,0" }
    $lnk.Save()
  }
  [void]$created.Add($path)
}

function Test-WebView2 {
  $id = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
  foreach ($key in @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$id", "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$id",
                     "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$id")) {
    try { $v = (Get-ItemProperty -Path $key -Name pv -ErrorAction Stop).pv; if ($v -and $v -ne "0.0.0.0") { return $v } } catch { }
  }
  return $null
}

Write-Host "Installation de ClubDirector AI (utilisateur : $env:USERNAME)$(if ($Simulation) { ' — SIMULATION, rien ne sera modifié' })"
Write-Host "Projet : $root"

# ---------------------------------------------------------------- 1. prérequis
Step "Prérequis"
$missing = @()
if (Get-Command uv -ErrorAction SilentlyContinue) { Write-Host "  uv : $((uv --version) -join ' ')" }
else { $missing += "uv (https://docs.astral.sh/uv/getting-started/installation/)" }
$sdks = @()
if (Get-Command dotnet -ErrorAction SilentlyContinue) { $sdks = @(dotnet --list-sdks 2>$null | Where-Object { $_ -match "^(8|9|10)\." }) }
if ($sdks.Count) { Write-Host "  .NET SDK : $($sdks[0])" } else { $missing += ".NET 8 SDK (https://dotnet.microsoft.com/download/dotnet/8.0)" }
$wv = Test-WebView2
if ($wv) { Write-Host "  WebView2 : $wv" } else { $missing += "Runtime WebView2 (https://developer.microsoft.com/microsoft-edge/webview2/)" }
if ($missing.Count) {
  Write-Warning ("À installer d'abord (rien n'est téléchargé automatiquement) :`n  - " + ($missing -join "`n  - "))
  if (-not $Simulation) { exit 1 }
}

# ---------------------------------------------------------------- 2. préparation
if (-not $SansPreparation) {
  Step "Préparation du service et du téléphone"
  Act "uv sync (dépendances Python du service)" { Push-Location (Join-Path $root "backend"); try { uv sync } finally { Pop-Location } }
  if (Get-Process ClubDirector.Overlay -ErrorAction SilentlyContinue) {
    Write-Warning "La fenêtre ClubDirector est ouverte : fermez-la (icône de la zone de notification > Quitter) puis relancez l'installation pour la recompiler."
  } else {
    Act "compilation de la fenêtre du téléphone (Release)" { dotnet build $overlayProj -c Release --nologo -v q | Out-Host }
  }
}

# ---------------------------------------------------------------- 3. données
Step "Données (%LOCALAPPDATA%\ClubDirectorAI)"
if (Test-Path $DossierDonnees) { Write-Host "  dossier existant conservé : $DossierDonnees" }
else { Act "création de $DossierDonnees" { New-Item -ItemType Directory -Path $DossierDonnees | Out-Null } }
$config = Join-Path $DossierDonnees "config.toml"
if (Test-Path $config) { Write-Host "  config.toml existant conservé" }
else { Act "config.toml créé depuis config\clubdirector.example.toml" { Copy-Item (Join-Path $root "config\clubdirector.example.toml") $config } }

# ---------------------------------------------------------------- 4. raccourcis
Step "Raccourcis"
$start = Join-Path $root "scripts\start_clubdirector.ps1"
if (-not $SansMenu) {
  New-Shortcut (Join-Path $DossierMenu "ClubDirector AI.lnk") $start "" "Lancer l'IA locale, le service et le téléphone ClubDirector"
  New-Shortcut (Join-Path $DossierMenu "Désinstaller ClubDirector AI.lnk") (Join-Path $root "scripts\uninstall_windows.ps1") "-Pause" "Retirer les raccourcis et le lancement au démarrage" -Visible
}
if ($Demarrage) {
  New-Shortcut (Join-Path $DossierDemarrage "ClubDirector AI.lnk") $start "" "ClubDirector AI au démarrage de Windows (service + téléphone)"
} else {
  Write-Host "  lancement au démarrage de Windows : non (relancer avec -Demarrage pour l'activer)"
}

# ---------------------------------------------------------------- manifeste
$manifest = Join-Path $DossierDonnees "install.json"
Act "inventaire de l'installation : $manifest" {
  $prev = @()
  if (Test-Path $manifest) { try { $prev = @((Get-Content $manifest -Raw -Encoding UTF8 | ConvertFrom-Json).raccourcis) } catch { } }
  $all = @($prev + $created | Where-Object { $_ } | Select-Object -Unique)
  $obj = [ordered]@{ projet = $root; installe_le = (Get-Date).ToString("s"); demarrage = [bool]$Demarrage; raccourcis = $all }
  $obj | ConvertTo-Json | Out-File -FilePath $manifest -Encoding utf8
}

Write-Host ""
Write-Host "Terminé. Lancer : menu Démarrer > ClubDirector AI, ou « Lancer ClubDirector.cmd » à la racine du projet." -ForegroundColor Green
Write-Host "Désinstaller : menu Démarrer > ClubDirector AI > Désinstaller, ou scripts\uninstall_windows.ps1"
