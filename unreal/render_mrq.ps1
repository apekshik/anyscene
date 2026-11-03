# Headless Movie Render Queue stills of a built level, one process per camera sequence (no editor, no window):
#   UnrealEditor-Cmd <uproject> <map> -game -LevelSequence=<SEQ> -MoviePipelineConfig=<CFG> -RenderOffscreen
#   powershell -File render_mrq.ps1 [-Cams cam_street,cam_table,cam_wok] [-Project ...] [-Dest /Game/AnyScene/HK] [-Level L_HK]
#                                   [-Config MRQ_Still|MRQ_Linear|MRQ_Clip] [-Cvars "r.Foo=1,r.Bar=2"]
# -Cvars adds console variables for an A/B render without rebuilding (they go into -dpcvars).
param(
  [string]$Project = "C:\Users\apek-anna\Developer\anyscene-unreal\AnySceneUE\AnySceneUE.uproject",
  [string]$Dest = "/Game/AnyScene/HK", [string]$Level = "L_HK",
  [string]$Cams = "cam_street,cam_table,cam_wok", [string]$Config = "MRQ_Still",
  [int]$ResX = 1920, [int]$ResY = 804, [string]$Cvars = ""
)
$ue = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
# Async compilation off (props render invisible / placeholder under -RenderOffscreen otherwise), Niagara waits for
# its shaders, no texture streaming (low mips in a short session).
$dp = "-dpcvars=Editor.AsyncAssetCompilation=0,Editor.AsyncTextureCompilation=0,Editor.AsyncStaticMeshCompilation=0,fx.Niagara.ForceWaitForCompilationOnActivate=1,r.TextureStreaming=0"
if ($Cvars) { $dp = "$dp,$Cvars" }
foreach ($c in $Cams.Split(",")) {
  $t = Measure-Command {
    & $ue $Project "$Dest/$Level" -game "-LevelSequence=$Dest/Sequences/SEQ_$c.SEQ_$c" "-MoviePipelineConfig=$Dest/MRQ/$Config.$Config" `
      -RenderOffscreen -windowed "-resx=$ResX" "-resy=$ResY" -unattended -nosplash -nop4 -nosound -notexturestreaming "-log=mrq_$c.log" `
      $dp | Out-Null
  }
  "$c $Config {0:N1}s" -f $t.TotalSeconds
}
