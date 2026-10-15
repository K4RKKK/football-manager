<#
  Audit de l'environnement ClubDirector AI (cahier des charges §3.1) — LECTURE SEULE.
  Ne modifie rien, n'installe rien. Produit audit-report.json dans le dossier courant.
  Usage : powershell -ExecutionPolicy Bypass -File scripts\audit_windows.ps1
#>
$ErrorActionPreference = "SilentlyContinue"
$r = [ordered]@{}

$os = Get-CimInstance Win32_OperatingSystem
$r.windows = @{ caption = $os.Caption; version = $os.Version; build = $os.BuildNumber }
$r.cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$r.ram_gb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$r.gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { @{ name = $_.Name; driver = $_.DriverVersion } })

# Installations FM26 : bibliothèques Steam + Epic
$candidates = @()
$steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam").SteamPath
if ($steam) {
  $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
  $libs = @($steam) + (Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\','\' })
  foreach ($l in $libs) { $candidates += (Join-Path $l "steamapps\common\Football Manager 26") }
}
$candidates += "C:\Program Files\Epic Games\FootballManager26"
$r.fm26 = @()
foreach ($c in ($candidates | Select-Object -Unique)) {
  if (Test-Path $c) {
    $exe = Get-ChildItem $c -Filter "fm.exe" | Select-Object -First 1
    $bep = Join-Path $c "BepInEx"
    $r.fm26 += @{
      path = $c
      platform = $(if ($c -like "*steamapps*") { "Steam" } elseif ($c -like "*Epic*") { "Epic" } else { "autre" })
      exe_version = $exe.VersionInfo.FileVersion
      il2cpp = (Test-Path (Join-Path $c "GameAssembly.dll"))
      unity_player = (Get-Item (Join-Path $c "UnityPlayer.dll")).VersionInfo.FileVersion
      bepinex = (Test-Path $bep)
      bepinex_core = @(Get-ChildItem (Join-Path $bep "core") -Filter "BepInEx*.dll" | ForEach-Object { "$($_.Name) $($_.VersionInfo.FileVersion)" })
      interop_generated = (Test-Path (Join-Path $bep "interop\UnityEngine.UIElementsModule.dll"))
      plugins = @(Get-ChildItem (Join-Path $bep "plugins") -Recurse -Filter *.dll | ForEach-Object { $_.FullName.Replace($c, "") })
      doorstop_ignore_disable = (Select-String -Path (Join-Path $c "doorstop_config.ini") -Pattern "ignore_disable_switch\s*=\s*true" -Quiet)
    }
  }
}

# Sauvegardes (noms et tailles seulement)
$docs = [Environment]::GetFolderPath("MyDocuments")
$saveDirs = @((Join-Path $docs "Sports Interactive\Football Manager 26\games"))
$r.saves = @()
foreach ($d in $saveDirs) {
  if (Test-Path $d) {
    $r.saves += @(Get-ChildItem $d -Recurse -Filter *.fm | Sort-Object LastWriteTime -Descending | Select-Object -First 20 |
      ForEach-Object { @{ path = $_.FullName; size_mb = [math]::Round($_.Length / 1MB, 1); modified = $_.LastWriteTime.ToString("s") } })
  }
}
$r.save_dirs_checked = $saveDirs

function Ver($cmd, $arg) { try { (& $cmd $arg 2>$null | Select-Object -First 1) } catch { $null } }
$r.tools = @{
  python = Ver "python" "--version"; uv = Ver "uv" "--version"; git = Ver "git" "--version"
  node = Ver "node" "--version"; dotnet = Ver "dotnet" "--version"
  ollama = Ver "ollama" "--version"; llama_server = [bool](Get-Command "llama-server" -ErrorAction SilentlyContinue)
  ilspy = [bool](Get-Command "ilspycmd" -ErrorAction SilentlyContinue)
}
$r.local_ai = @{}
foreach ($u in @("http://127.0.0.1:8080/v1/models", "http://127.0.0.1:11434/v1/models")) {
  try { $r.local_ai[$u] = (Invoke-RestMethod $u -TimeoutSec 2).data.id } catch { $r.local_ai[$u] = $null }
}

$r | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 audit-report.json
Write-Host "Rapport écrit : $(Resolve-Path audit-report.json)"
