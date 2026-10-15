<#
  Désinstalle ClubDirector AI pour l'utilisateur courant :
  - ferme la fenêtre du téléphone et arrête le service ClubDirector s'ils tournent (-SansArret pour les laisser) ;
  - retire les raccourcis créés par install_windows.ps1 (menu Démarrer, lancement au démarrage de Windows) ;
  - garde vos données (base, conversations, réglages) sauf avec -SupprimerDonnees, après confirmation ;
  - ne touche jamais aux sauvegardes FM26 ni au dossier du projet (à supprimer vous-même si vous le souhaitez).

  Usage : powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1 [-SupprimerDonnees] [-SansArret] [-Simulation]
#>
param(
  [switch]$SupprimerDonnees, [switch]$SansArret, [switch]$Simulation, [switch]$Pause,
  [string]$DossierDonnees = (Join-Path $env:LOCALAPPDATA "ClubDirectorAI"),
  [string]$DossierMenu = (Join-Path ([Environment]::GetFolderPath("Programs")) "ClubDirector AI"),
  [string]$DossierDemarrage = [Environment]::GetFolderPath("Startup"),
  [int]$Port = 8765
)
$ErrorActionPreference = "Stop"
function Act([string]$text, [scriptblock]$action) {
  if ($Simulation) { Write-Host "  [simulation] $text" } else { Write-Host "  $text"; & $action }
}
Write-Host "Désinstallation de ClubDirector AI$(if ($Simulation) { ' — SIMULATION, rien ne sera modifié' })"

# ---------------------------------------------------------------- arrêt
if (-not $SansArret) {
  foreach ($p in @(Get-Process ClubDirector.Overlay -ErrorAction SilentlyContinue)) {
    Act "fermeture de la fenêtre du téléphone (processus $($p.Id))" { Stop-Process -Id $p.Id -Confirm:$false }
  }
  # Le service : seulement le processus qui écoute sur son port ET porte un nom attendu.
  try { $owners = @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique) }
  catch { $owners = @() }
  foreach ($procId in $owners) {
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p -and @("clubdirector", "python", "uv") -contains $p.ProcessName.ToLower()) {
      Act "arrêt du service ClubDirector sur 127.0.0.1:$Port (processus $procId)" { Stop-Process -Id $procId -Confirm:$false }
    } elseif ($p) {
      Write-Warning "Le port $Port est tenu par « $($p.ProcessName) » : laissé tel quel."
    }
  }
}

# ---------------------------------------------------------------- raccourcis
$manifest = Join-Path $DossierDonnees "install.json"
$links = @((Join-Path $DossierDemarrage "ClubDirector AI.lnk"), (Join-Path $DossierMenu "ClubDirector AI.lnk"),
           (Join-Path $DossierMenu "Désinstaller ClubDirector AI.lnk"))
if (Test-Path $manifest) { try { $links += @((Get-Content $manifest -Raw -Encoding UTF8 | ConvertFrom-Json).raccourcis) } catch { } }
foreach ($l in ($links | Where-Object { $_ } | Select-Object -Unique)) {
  # Seuls des raccourcis .lnk portant le nom de ClubDirector sont retirés.
  if ((Test-Path -LiteralPath $l) -and $l.EndsWith(".lnk") -and (Split-Path $l -Leaf) -like "*ClubDirector*") {
    Act "raccourci retiré : $l" { Remove-Item -LiteralPath $l -Confirm:$false }
  }
}
if (Test-Path -LiteralPath $DossierMenu) {
  # Le dossier du menu Démarrer n'est retiré que s'il ne contient que nos raccourcis.
  $others = @(Get-ChildItem -LiteralPath $DossierMenu -Force | Where-Object { $_.Name -notlike "*ClubDirector*.lnk" })
  if (-not $others.Count) { Act "dossier du menu Démarrer retiré : $DossierMenu" { Remove-Item -LiteralPath $DossierMenu -Recurse -Confirm:$false } }
}
if (Test-Path $manifest) { Act "inventaire retiré : $manifest" { Remove-Item -LiteralPath $manifest -Confirm:$false } }

# ---------------------------------------------------------------- données
if ($SupprimerDonnees -and (Test-Path $DossierDonnees)) {
  Write-Warning "Suppression DÉFINITIVE de $DossierDonnees (base, conversations, réglages, copies de sauvegardes). Vos sauvegardes FM26 ne sont pas touchées."
  if ($Simulation) { Write-Host "  [simulation] suppression de $DossierDonnees" }
  elseif ((Read-Host "Tapez SUPPRIMER pour confirmer") -ceq "SUPPRIMER") { Remove-Item -LiteralPath $DossierDonnees -Recurse -Confirm:$false; Write-Host "  données supprimées" }
  else { Write-Host "  données conservées" }
} else {
  Write-Host "  données conservées : $DossierDonnees"
}
Write-Host ""
Write-Host "Terminé. Le dossier du projet n'a pas été supprimé." -ForegroundColor Green
if ($Pause) { Read-Host "Appuyez sur Entrée pour fermer" | Out-Null }
