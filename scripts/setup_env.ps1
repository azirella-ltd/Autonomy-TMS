$hostname = $env:COMPUTERNAME
$hostEnv = ".env.$hostname"

if (Test-Path $hostEnv) {
    Copy-Item $hostEnv ".env" -Force
    Write-Host "Loaded environment from $hostEnv"
}
elseif (Test-Path ".env.local") {
    Copy-Item ".env.local" ".env" -Force
    Write-Host "Loaded environment from .env.local"
}
else {
    Copy-Item ".env.example" ".env" -Force
    Write-Host "Created .env from .env.example"
}
