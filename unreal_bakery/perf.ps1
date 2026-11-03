# Standalone (-game) real-time performance run of a built AnyScene level, with no window (-RenderOffscreen).
# Captures N frames with the CSV profiler (frame/game/render/GPU times) from the PlayerStart (hero camera), and samples
# total GPU memory with nvidia-smi before and during the run.
#   powershell -File perf.ps1 [-Map /Game/AnyScene/HK/L_HK] [-ResX 2560] [-ResY 1440] [-Frames 900] [-Extra "r.Lumen.HardwareRayTracing 0"]
param(
  [string]$Project = "C:\Users\apek-anna\Developer\anyscene-unreal\AnySceneUE\AnySceneUE.uproject",
  [string]$Map = "/Game/AnyScene/HK/L_HK",
  [int]$ResX = 2560, [int]$ResY = 1440, [int]$Frames = 900, [int]$TimeoutS = 600,
  [string]$Tag = "perf", [string]$Extra = ""
)
$ue = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$saved = Join-Path (Split-Path $Project) "Saved"
$csvDir = Join-Path $saved "Profiling\CSV"
$before = Get-ChildItem $csvDir -Filter *.csv -ErrorAction SilentlyContinue | ForEach-Object FullName
$mem0 = [int](& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
# -resx/-resy are ignored under -RenderOffscreen (the CSV showed 1066x600): r.setres sets the real size.
# The bare cvar names print their current values to the log (proof that Lumen / Nanite / volumetric fog are on).
$cmds = "r.setres ${ResX}x${ResY}w,r.DynamicGlobalIlluminationMethod,r.ReflectionMethod,r.Nanite,r.VolumetricFog,r.Lumen.HardwareRayTracing,r.RayTracing,r.Shadow.Virtual.Enable,t.MaxFPS 0,r.VSync 0,r.GPUCsvStatsEnabled 1,csvprofile frames=$Frames"
if ($Extra) { $cmds = "$Extra,$cmds" }
$args = @($Project, $Map, "-game", "-RenderOffscreen", "-windowed", "-resx=$ResX", "-resy=$ResY", "-unattended", "-nosplash",
          "-nop4", "-nosound", "-log=$Tag.log", "`"-ExecCmds=$cmds`"",
          "-dpcvars=Editor.AsyncAssetCompilation=0,Editor.AsyncTextureCompilation=0,Editor.AsyncStaticMeshCompilation=0,fx.Niagara.ForceWaitForCompilationOnActivate=1")  # async compilation leaves props invisible (render_shots.py); PS 5.1 Start-Process does not quote array items
$proc = Start-Process -FilePath $ue -ArgumentList $args -PassThru
$peak = $mem0
$sw = [Diagnostics.Stopwatch]::StartNew()
$csv = $null
while (-not $proc.HasExited -and $sw.Elapsed.TotalSeconds -lt $TimeoutS) {
  Start-Sleep -Seconds 2
  $m = [int](& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  if ($m -gt $peak) { $peak = $m }
  $new = Get-ChildItem $csvDir -Filter *.csv -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.FullName }
  if ($new) {
    $f = $new | Sort-Object LastWriteTime | Select-Object -Last 1
    # The CSV is written when the capture ends; wait until the file stops growing.
    $s1 = $f.Length; Start-Sleep -Seconds 3; $s2 = (Get-Item $f.FullName).Length
    if ($s1 -eq $s2 -and $s2 -gt 0) { $csv = $f.FullName; break }
  }
}
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
"gpu_mem_before_mb=$mem0 gpu_mem_peak_mb=$peak delta_mb=$($peak - $mem0)"
"csv=$csv"
