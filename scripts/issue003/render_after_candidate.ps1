param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PowerPoint', 'WPS')]
    [string]$ApplicationName,

    [string]$Candidate = 'docs/evidence/issue003/after/after-agent-authoring.pptx'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$candidatePath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $Candidate))
$evidenceRoot = [IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot 'docs\evidence\issue003\after')
)
if (-not $candidatePath.StartsWith($evidenceRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Candidate must remain inside docs/evidence/issue003/after'
}
if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
    throw "Candidate does not exist: $candidatePath"
}

$slug = $ApplicationName.ToLowerInvariant()
$renderDir = Join-Path $evidenceRoot ("renders\" + $slug)
if (Test-Path -LiteralPath $renderDir) {
    if (@(Get-ChildItem -LiteralPath $renderDir -Force).Count -gt 0) {
        throw "Render evidence already exists: $renderDir"
    }
}
else {
    [void](New-Item -ItemType Directory -Path $renderDir)
}

$progId = if ($ApplicationName -eq 'PowerPoint') {
    'PowerPoint.Application'
}
else {
    'KWPP.Application'
}
$application = $null
$presentation = $null
try {
    $application = New-Object -ComObject $progId
    try { $application.DisplayAlerts = 1 } catch { }
    $presentation = $application.Presentations.Open($candidatePath, -1, 0, 0)
    $slideCount = [int]$presentation.Slides.Count
    if ($slideCount -ne 10) {
        throw "Candidate opened with $slideCount slides instead of the frozen 10-page roster"
    }
    $repairsSupported = $null -ne (
        $presentation | Get-Member -Name Repairs -MemberType Property
    )
    $repairCount = if ($repairsSupported) {
        [int]$presentation.Repairs.Count
    }
    else {
        $null
    }
    if ($repairsSupported -and $repairCount -ne 0) {
        throw "$ApplicationName reported $repairCount package repairs"
    }
    $presentation.Export($renderDir, 'PNG', 1280, 720)
    $pngCount = @(Get-ChildItem -LiteralPath $renderDir -Filter '*.png' -File).Count
    if ($pngCount -ne $slideCount) {
        throw "$ApplicationName exported $pngCount PNG files for $slideCount slides"
    }
    $evidence = [ordered]@{
        schemaVersion = 1
        status = 'passed'
        candidate = [ordered]@{
            path = (Resolve-Path -Relative $candidatePath)
            sha256 = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
            sizeBytes = (Get-Item -LiteralPath $candidatePath).Length
        }
        application = [ordered]@{
            requestedName = $ApplicationName
            name = [string]$application.Name
            version = [string]$application.Version
            build = [string]$application.Build
            path = [string]$application.Path
            progId = $progId
        }
        compatibility = [ordered]@{
            slideCount = $slideCount
            pngCount = $pngCount
            repairsCollectionSupported = $repairsSupported
            repairCount = $repairCount
        }
    }
    $evidence | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $evidenceRoot ("office-" + $slug + '.json')) -Encoding utf8
    Write-Output "$ApplicationName opened and rendered $pngCount/10 slides without repairs"
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)
    }
    if ($null -ne $application) {
        try { $application.Quit() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
