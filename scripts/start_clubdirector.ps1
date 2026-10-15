<#
  Lance tout ClubDirector AI : l'IA locale (llama-server) puis le service (http://127.0.0.1:8765).
  - L'IA est démarrée dans sa propre fenêtre réduite si elle ne répond pas déjà sur 127.0.0.1:8080.
  - Le service attend que l'IA soit prête (chargement du modèle : ~10-60 s), puis démarre.
  Par défaut l'IA démarre en MODE JEU (moins de mémoire vidéo, pour jouer à FM26 en même temps).
  Usage : double-cliquer « Lancer ClubDirector.cmd » à la racine du projet,
          ou : powershell -ExecutionPolicy Bypass -File scripts\start_clubdirector.ps1 [-SansIA] [-PleinePuissance]
#>
param([switch]$SansIA, [switch]$PleinePuissance)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$llmUrl = "http://127.0.0.1:8080/health"

function Test-Llm {
  try { (Invoke-RestMethod $llmUrl -TimeoutSec 2).status -eq "ok" } catch { $false }
}

if (-not $SansIA) {
  if (Test-Llm) {
    Write-Host "IA locale déjà prête sur 127.0.0.1:8080."
  } else {
    Write-Host "Démarrage de l'IA locale (fenêtre réduite « ClubDirector IA »)..."
    Start-Process powershell -WindowStyle Minimized -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit",
      "-Command", "`$host.UI.RawUI.WindowTitle = 'ClubDirector IA'; & '$PSScriptRoot\start_llm.ps1' $(if ($PleinePuissance) { '' } else { '-ModeJeu' })"
    )
    $deadline = (Get-Date).AddMinutes(3)
    while (-not (Test-Llm)) {
      if ((Get-Date) -gt $deadline) {
        Write-Warning "L'IA ne répond pas après 3 minutes : le service démarre quand même (questions factuelles seulement). Voir la fenêtre « ClubDirector IA »."
        break
      }
      Start-Sleep -Seconds 2
    }
    if (Test-Llm) { Write-Host "IA locale prête." }
  }
}

Write-Host "Démarrage du service ClubDirector : http://127.0.0.1:8765"
Set-Location (Join-Path $root "backend")
uv run clubdirector serve
