# Script to copy project to short path and build
$SourcePath = "c:\Users\jeron\.gemini\antigravity\scratch\notifyinvest\mobile"
$DestPath = "C:\tmp\notify"

Write-Host "Stopping Gradle Daemons to release locks..."
Set-Location "$SourcePath\android"
.\gradlew.bat --stop
Start-Sleep -Seconds 3

Write-Host "Cleaning previous build folder..."
if (Test-Path $DestPath) { Remove-Item -Recurse -Force $DestPath }
New-Item -ItemType Directory -Force -Path $DestPath | Out-Null

Write-Host "Copying project files (excluding heavy build artifacts)..."
# Robocopy is faster and has better exclusion support
robocopy $SourcePath $DestPath /E /XD node_modules .expo .gradle build .cxx /XF *.iml

Write-Host "Installing dependencies in new location..."
Set-Location $DestPath
npm install

Write-Host "Building APK..."
Set-Location "$DestPath\android"
.\gradlew.bat assembleRelease
