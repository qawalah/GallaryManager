# DevStore "prepare" step: runs after PyInstaller, with $env:DEVSTORE_OUT set to
# the built folder (dist\photo-manager). Puts the few files the app reads from
# beside its own code into the frozen app's _internal folder, which is what
# os.path.dirname(os.path.dirname(__file__)) points at once it is frozen:
#   - the tray icon (windows\PhotoManager.ico)
#   - the task and core sources plus app\registry.py and app\page.py, which the
#     wording tool (app\wordsource.py) reads as text
$ErrorActionPreference = 'Stop'
$internal = Join-Path $env:DEVSTORE_OUT '_internal'
if (-not (Test-Path $internal)) { Write-Output "::error::$internal not found"; exit 1 }
Copy-Item 'windows\PhotoManager.ico' $internal -Force
foreach ($d in @('app\tasks', 'core')) {
    $to = Join-Path $internal $d
    New-Item -ItemType Directory -Path $to -Force | Out-Null
    Copy-Item "$d\*.py" $to -Force
}
$app = Join-Path $internal 'app'
New-Item -ItemType Directory -Path $app -Force | Out-Null
Copy-Item 'app\registry.py', 'app\page.py' $app -Force
Write-Output "Prepared $internal"
exit 0
