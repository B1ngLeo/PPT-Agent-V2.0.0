param(
    [string]$BaselineRoot = "docs/evidence/issue003/baseline"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$baselineDir = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $BaselineRoot))
$expectedParent = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "docs\evidence\issue003"))
if (-not $baselineDir.StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BaselineRoot must remain inside docs/evidence/issue003"
}
if (-not (Test-Path -LiteralPath $baselineDir -PathType Container)) {
    throw "Baseline directory does not exist: $baselineDir"
}

$decks = [ordered]@{
    "reference-ppt-master" = "reference-ppt-master.pptx"
    "before-deterministic-template" = "before-deterministic-template.pptx"
    "before-user-download" = "before-user-download.pptx"
}
$application = $null
$presentations = @()
try {
    $application = New-Object -ComObject "PowerPoint.Application"
    try { $application.DisplayAlerts = 1 } catch { }
    foreach ($entry in $decks.GetEnumerator()) {
        $pptx = Join-Path $baselineDir $entry.Value
        if (-not (Test-Path -LiteralPath $pptx -PathType Leaf)) {
            continue
        }
        $renderDir = Join-Path $baselineDir ("renders\" + $entry.Key)
        [void](New-Item -ItemType Directory -Path $renderDir -Force)
        Get-ChildItem -LiteralPath $renderDir -Filter "*.png" -File -ErrorAction SilentlyContinue |
            Remove-Item -Force
        $presentation = $null
        try {
            $presentation = $application.Presentations.Open($pptx, -1, 0, 0)
            $slideCount = [int]$presentation.Slides.Count
            $repairsSupported = $null -ne ($presentation | Get-Member -Name Repairs -MemberType Property)
            $repairCount = if ($repairsSupported) { [int]$presentation.Repairs.Count } else { $null }
            $presentation.Export($renderDir, "PNG", 1280, 720)
            $pngCount = @(Get-ChildItem -LiteralPath $renderDir -Filter "*.png" -File).Count
            if ($pngCount -ne $slideCount) {
                throw "$($entry.Key) exported $pngCount PNG files for $slideCount slides"
            }
            if ($repairsSupported -and $repairCount -ne 0) {
                throw "$($entry.Key) reported $repairCount package repairs"
            }
            $presentations += [ordered]@{
                name = $entry.Key
                slideCount = $slideCount
                pngCount = $pngCount
                repairsCollectionSupported = $repairsSupported
                repairCount = $repairCount
            }
        }
        finally {
            if ($null -ne $presentation) {
                $presentation.Close()
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)
            }
        }
    }
    $evidence = [ordered]@{
        schemaVersion = 1
        application = [ordered]@{
            name = [string]$application.Name
            version = [string]$application.Version
            build = [string]$application.Build
            path = [string]$application.Path
        }
        decks = $presentations
    }
    $evidence | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $baselineDir "powerpoint-render-evidence.json") -Encoding utf8
    Write-Output "Rendered $($presentations.Count) ISSUE-003 baseline decks with PowerPoint"
}
finally {
    if ($null -ne $application) {
        try { $application.Quit() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
