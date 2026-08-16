param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PowerPoint', 'WPS')]
    [string]$ApplicationName,

    [ValidateRange(1, 5)]
    [int]$MaxAttempts = 3
)

$verificationScript = Join-Path $PSScriptRoot 'verify-office-compatibility.ps1'
$lastExitCode = 1

for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verificationScript -ApplicationName $ApplicationName
    $lastExitCode = $LASTEXITCODE
    if ($lastExitCode -eq 0) {
        exit 0
    }

    if ($attempt -lt $MaxAttempts) {
        Write-Warning "$ApplicationName compatibility attempt $attempt/$MaxAttempts failed; retrying after COM cleanup."
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
        Start-Sleep -Seconds 2
    }
}

Write-Error "$ApplicationName compatibility failed after $MaxAttempts bounded attempts."
exit $lastExitCode
