$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PORT = '8766'
Write-Host 'RenewSure: http://127.0.0.1:8766'
Write-Host 'Keep this window open. The server restarts automatically after an unexpected failure.'
while ($true) {
    python server.py
    if ($LASTEXITCODE -eq 0) { break }
    Write-Host 'Server stopped unexpectedly. Retrying in 3 seconds. Press Ctrl+C to stop.'
    Start-Sleep -Seconds 3
}
