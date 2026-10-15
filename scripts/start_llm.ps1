<#
  Démarre l'IA locale de ClubDirector : llama-server (llama.cpp, Vulkan) sur 127.0.0.1:8080.
  Chemins configurables par variables d'environnement (aucun chemin n'est supposé standard) :
    CLUBDIRECTOR_LLM_SERVER  chemin de llama-server.exe
    CLUBDIRECTOR_LLM_MODEL   chemin du modèle .gguf
    CLUBDIRECTOR_LLM_DEVICE  périphérique Vulkan (défaut Vulkan0 = carte dédiée ; voir --list-devices)
  Usage : powershell -ExecutionPolicy Bypass -File scripts\start_llm.ps1 [-Ctx 32768] [-Port 8080]
#>
param(
  [int]$Port = 8080,
  [int]$Ctx = 32768
)
$ErrorActionPreference = "Stop"
$server = if ($env:CLUBDIRECTOR_LLM_SERVER) { $env:CLUBDIRECTOR_LLM_SERVER } else { "C:\AI\llama.cpp-b11658-vulkan\llama-server.exe" }
$model  = if ($env:CLUBDIRECTOR_LLM_MODEL)  { $env:CLUBDIRECTOR_LLM_MODEL }  else { "C:\AI\models\gemma-4-26B-A4B-it\gemma-4-26B-A4B-it-UD-IQ4_XS.gguf" }
$device = if ($env:CLUBDIRECTOR_LLM_DEVICE) { $env:CLUBDIRECTOR_LLM_DEVICE } else { "Vulkan0" }
foreach ($p in @($server, $model)) { if (-not (Test-Path $p)) { throw "Introuvable : $p" } }

# --host 127.0.0.1 : jamais exposé sur le réseau. --jinja : modèle de conversation du GGUF (appels d'outils).
# -ngl 999 : toutes les couches sur la carte ; cache KV en q8_0 pour tenir 32k de contexte dans 16 Go.
& $server `
  -m $model `
  --host 127.0.0.1 --port $Port `
  --device $device -ngl 999 `
  -c $Ctx -fa on -ctk q8_0 -ctv q8_0 `
  -np 1 `
  --jinja `
  --alias clubdirector-local
