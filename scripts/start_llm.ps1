<#
  Démarre l'IA locale de ClubDirector : llama-server (llama.cpp, Vulkan) sur 127.0.0.1:8080.
  Chemins configurables par variables d'environnement (aucun chemin n'est supposé standard) :
    CLUBDIRECTOR_LLM_SERVER  chemin de llama-server.exe
    CLUBDIRECTOR_LLM_MODEL   chemin du modèle .gguf
    CLUBDIRECTOR_LLM_DEVICE  périphérique Vulkan (défaut Vulkan0 = carte dédiée ; voir --list-devices)
  Usage : powershell -ExecutionPolicy Bypass -File scripts\start_llm.ps1 [-Ctx 32768] [-Port 8080] [-ModeJeu] [-Journal <fichier>]
  -Journal : journal du serveur (défaut %LOCALAPPDATA%\ClubDirectorAI\llm.log). Le précédent est archivé
             (llm-AAAAMMJJ-HHMMSS.log, 5 gardés) : après un blocage, sa trace reste disponible.
  La surveillance du service (backend ai/llm_watchdog.py) relance ce script, avec les mêmes paramètres,
  si le serveur se fige ou s'arrête.
  -ModeJeu : à utiliser pendant que FM26 tourne. Les « experts » MoE de -CoucheCpu couches (défaut 12/30)
             restent en mémoire vive au lieu de la carte graphique : moins de VRAM prise au jeu,
             génération plus lente. Mesuré sur RX 9070 XT (Gemma 4 26B-A4B, contexte 32k) :
               pleine puissance : 14,9 Go de VRAM, ~116 tokens/s
               -ModeJeu (12)    : 11,4 Go de VRAM, ~41 tokens/s
               -ModeJeu -CoucheCpu 20 : 8,7 Go de VRAM, ~29 tokens/s
             En match 3D (FM26 ≈ 3,5 Go), mesuré le 15/10/2026 avec scripts\mesure_llm.ps1 : 12 couches → carte à
             15,4 Go sur 16, ≈ 34 tokens/s ; 8 couches → carte saturée (15,6 Go, débordement en mémoire partagée,
             FM26 perd de la VRAM) pour ≈ 35 tokens/s : 12 reste le réglage du mode jeu.
#>
param(
  [int]$Port = 8080,
  [int]$Ctx = 32768,
  [switch]$ModeJeu,
  [int]$CoucheCpu = 12,
  [string]$Journal = ""
)
$ErrorActionPreference = "Stop"
$server = if ($env:CLUBDIRECTOR_LLM_SERVER) { $env:CLUBDIRECTOR_LLM_SERVER } else { "C:\AI\llama.cpp-b11658-vulkan\llama-server.exe" }
$model  = if ($env:CLUBDIRECTOR_LLM_MODEL)  { $env:CLUBDIRECTOR_LLM_MODEL }  else { "C:\AI\models\gemma-4-26B-A4B-it\gemma-4-26B-A4B-it-UD-IQ4_XS.gguf" }
$device = if ($env:CLUBDIRECTOR_LLM_DEVICE) { $env:CLUBDIRECTOR_LLM_DEVICE } else { "Vulkan0" }
foreach ($p in @($server, $model)) { if (-not (Test-Path $p)) { throw "Introuvable : $p" } }

if (-not $Journal) { $Journal = Join-Path $env:LOCALAPPDATA "ClubDirectorAI\llm.log" }
$logDir = Split-Path $Journal -Parent
New-Item -ItemType Directory -Force $logDir | Out-Null
if (Test-Path $Journal) {
  $archive = Join-Path $logDir ("llm-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
  try { Move-Item $Journal $archive -ErrorAction Stop } catch { $Journal = $archive }  # encore ouvert : nouveau nom
  Get-ChildItem $logDir -Filter "llm-2*.log" | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 5 | Remove-Item -ErrorAction SilentlyContinue
}
Write-Host "Journal du serveur : $Journal"

# --host 127.0.0.1 : jamais exposé sur le réseau. --jinja : modèle de conversation du GGUF (appels d'outils).
# -ngl 999 : toutes les couches sur la carte ; cache KV en q8_0 pour tenir 32k de contexte dans 16 Go.
$extra = @()
if ($ModeJeu) { $extra += @("--n-cpu-moe", "$CoucheCpu") }

& $server `
  -m $model `
  --host 127.0.0.1 --port $Port `
  --device $device -ngl 999 `
  -c $Ctx -fa on -ctk q8_0 -ctv q8_0 `
  -np 1 `
  --jinja `
  --alias clubdirector-local `
  --log-file $Journal --log-colors off `
  @extra
