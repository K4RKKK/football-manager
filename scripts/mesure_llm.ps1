<#
  Mesure de l'IA locale en situation de jeu : mémoire vidéo (carte entière, llama-server, FM26) et
  vitesse de génération (jetons/s), pour choisir -CoucheCpu de start_llm.ps1 (couches MoE sur le CPU).
  Lecture seule, sauf une courte génération (256 jetons) par essai sur llama-server.
  Usage : powershell -ExecutionPolicy Bypass -File scripts\mesure_llm.ps1 [-Essais 3] [-Port 8080]
  À lancer FM26 ouvert, de préférence pendant un match en 3D (le moment où le jeu prend le plus de VRAM).
#>
param([int]$Essais = 3, [int]$Port = 8080)
$ErrorActionPreference = "Stop"

function Get-Vram {
  $adapter = (Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples |
    Sort-Object CookedValue -Descending | Select-Object -First 1
  $byPid = @{}
  foreach ($s in (Get-Counter '\GPU Process Memory(*)\Dedicated Usage').CounterSamples) {
    if ($s.InstanceName -match 'pid_(\d+)_') { $byPid[[int]$matches[1]] += $s.CookedValue }  # une ligne par carte
  }
  $one = { param($name) $p = Get-Process -Name $name -ErrorAction SilentlyContinue | Select-Object -First 1
           if ($p -and $byPid.ContainsKey($p.Id)) { [math]::Round($byPid[$p.Id] / 1GB, 2) } else { $null } }
  [pscustomobject]@{
    CarteGo = [math]::Round($adapter.CookedValue / 1GB, 2)
    LlamaGo = & $one "llama-server"
    FM26Go  = & $one "fm"
  }
}

$server = Get-CimInstance Win32_Process -Filter "name='llama-server.exe'" | Select-Object -First 1
if (-not $server) { throw "llama-server ne tourne pas." }
$moe = if ($server.CommandLine -match '--n-cpu-moe\s+(\d+)') { [int]$matches[1] } else { 0 }
Write-Host ("llama-server : --n-cpu-moe {0} (couches MoE sur le CPU)" -f $moe)
$before = Get-Vram
Write-Host ("VRAM avant : carte {0} Go, llama-server {1} Go, FM26 {2} Go" -f $before.CarteGo, $before.LlamaGo, $before.FM26Go)

$body = @{ prompt = "Rapport du directeur sportif sur l'effectif, en français, en détail :"; n_predict = 256;
           temperature = 0; ignore_eos = $true; cache_prompt = $false } | ConvertTo-Json
$rates = @()
for ($i = 1; $i -le $Essais; $i++) {
  $r = Invoke-RestMethod "http://127.0.0.1:$Port/completion" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
    -ContentType "application/json" -TimeoutSec 300
  $rates += [double]$r.timings.predicted_per_second
  Write-Host ("Essai {0} : {1:N1} jetons/s ({2} jetons)" -f $i, $r.timings.predicted_per_second, $r.timings.predicted_n)
}
$after = Get-Vram
$median = ($rates | Sort-Object)[[int][math]::Floor(($rates.Count - 1) / 2)]
Write-Host ("Résultat : --n-cpu-moe {0} ; médiane {1:N1} jetons/s ; VRAM carte {2} Go / 16 (max avant-après), FM26 {3} Go" -f `
  $moe, $median, [math]::Max($before.CarteGo, $after.CarteGo), $after.FM26Go)
