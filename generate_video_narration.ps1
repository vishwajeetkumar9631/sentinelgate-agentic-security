$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$segments = Get-Content -LiteralPath (Join-Path $root 'video_narration.json') -Raw | ConvertFrom-Json
$clipDirectory = Join-Path $root 'narration_clips'
New-Item -ItemType Directory -Force -Path $clipDirectory | Out-Null

for ($index = 0; $index -lt $segments.Count; $index++) {
    $voice = New-Object -ComObject SAPI.SpVoice
    $selected = $voice.GetVoices() | Where-Object { $_.GetDescription() -like '*Zira*' } | Select-Object -First 1
    if ($selected) { $voice.Voice = $selected }
    $voice.Rate = 1
    $stream = New-Object -ComObject SAPI.SpFileStream
    $clip = Join-Path $clipDirectory ('scene_{0:d2}.wav' -f ($index + 1))
    $stream.Open($clip, 3, $false)
    $voice.AudioOutputStream = $stream
    [void]$voice.Speak([string]$segments[$index].narration)
    $stream.Close()
    Write-Output ('Created {0}' -f $clip)
}
