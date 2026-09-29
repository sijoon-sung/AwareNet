$ErrorActionPreference = 'Stop'
$demoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$demoOutput = Join-Path $demoRoot 'output/healthcare_enterprise_demo'
$demoScenes = Get-Content -LiteralPath (Join-Path $demoOutput 'storyboard.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$demoSpeech = New-Object System.Speech.Synthesis.SpeechSynthesizer
$demoSpeech.SelectVoice('Microsoft Heami Desktop')
$demoSpeech.Rate = 1
$demoSpeech.Volume = 100
try {
    foreach ($demoScene in $demoScenes) {
        $demoAudio = Join-Path $demoOutput ('narration/' + $demoScene.id + '.wav')
        $demoSpeech.SetOutputToWaveFile($demoAudio)
        $demoSpeech.Speak($demoScene.narration)
        $demoSpeech.SetOutputToNull()
        Write-Output $demoScene.id
    }
} finally {
    $demoSpeech.Dispose()
}
