# Headless Movie Render Queue stills of a built level, one process per camera sequence (no editor, no window):
#   UnrealEditor-Cmd <uproject> <map> -game -LevelSequence=<SEQ> -MoviePipelineConfig=<CFG> -RenderOffscreen
#   powershell -File render_mrq.ps1 [-Cams cam_street,cam_table,cam_wok] [-Config MRQ_Still|MRQ_Linear]
param(
  [string]$Project = "C:\Users\apek-anna\Developer\anyscene-unreal\AnySceneUE\AnySceneUE.uproject",
  [string]$Dest = "/Game/AnyScene/HK", [string]$Level = "L_HK",
  [string]$Cams = "cam_street,cam_table,cam_wok", [string]$Config = "MRQ_Still"
)
$ue = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
foreach ($c in $Cams.Split(",")) {
  $t = Measure-Command {
    & $ue $Project "$Dest/$Level" -game "-LevelSequence=$Dest/Sequences/SEQ_$c.SEQ_$c" "-MoviePipelineConfig=$Dest/MRQ/$Config.$Config" `
      -RenderOffscreen -windowed -resx=1920 -resy=804 -unattended -nosplash -nop4 -nosound -notexturestreaming "-log=mrq_$c.log" `
      "-dpcvars=Editor.AsyncAssetCompilation=0" | Out-Null
  }
  "$c $Config {0:N1}s" -f $t.TotalSeconds
}
