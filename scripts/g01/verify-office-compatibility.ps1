param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PowerPoint', 'WPS')]
    [string]$ApplicationName
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$progId = if ($ApplicationName -eq 'PowerPoint') { 'PowerPoint.Application' } else { 'KWPP.Application' }
$evidenceName = if ($ApplicationName -eq 'PowerPoint') { 'g01-powerpoint-compatibility.json' } else { 'g01-wps-compatibility.json' }
$exportRoot = Join-Path $repositoryRoot ".tmp\compatibility\$($ApplicationName.ToLowerInvariant())"
$evidencePath = Join-Path $repositoryRoot "docs\evidence\$evidenceName"

function Get-EditableTextCount {
    param([object]$Shapes)
    $count = 0
    for ($index = 1; $index -le $Shapes.Count; $index++) {
        $shape = $Shapes.Item($index)
        if ($shape.Type -eq 6) {
            $count += Get-EditableTextCount -Shapes $shape.GroupItems
        }
        elseif ($shape.HasTextFrame -ne 0 -and $shape.TextFrame.HasText -ne 0) {
            $count++
        }
    }
    return $count
}

$application = $null
$results = @()
try {
    $application = New-Object -ComObject $progId
    try { $application.DisplayAlerts = 1 } catch { }
    $applicationInfo = [ordered]@{
        requestedApplication = $ApplicationName
        progId = $progId
        reportedName = [string]$application.Name
        version = [string]$application.Version
        build = [string]$application.Build
        executableRoot = [string]$application.Path
        displayAlerts = 'suppressed-for-automation'
    }
    $decks = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'tests\golden') -Filter deck.pptx -File -Recurse |
        Where-Object { $_.FullName -match '[\\/]generated[\\/]render[\\/]deck\.pptx$' } |
        Sort-Object FullName
    if ($decks.Count -ne 10) {
        throw "Expected 10 generated golden decks, found $($decks.Count)"
    }
    foreach ($deck in $decks) {
        $caseName = Split-Path (Split-Path (Split-Path $deck.DirectoryName -Parent) -Parent) -Leaf
        $caseExport = Join-Path $exportRoot $caseName
        [void](New-Item -ItemType Directory -Path $caseExport -Force)
        Get-ChildItem -LiteralPath $caseExport -Filter *.png -File -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
        $presentation = $null
        try {
            $presentation = $application.Presentations.Open($deck.FullName, -1, 0, 0)
            $slideCount = [int]$presentation.Slides.Count
            $editableTextCount = 0
            for ($slideIndex = 1; $slideIndex -le $slideCount; $slideIndex++) {
                $editableTextCount += Get-EditableTextCount -Shapes $presentation.Slides.Item($slideIndex).Shapes
            }
            $repairsSupported = $null -ne ($presentation | Get-Member -Name Repairs -MemberType Property)
            $repairCount = if ($repairsSupported) { [int]$presentation.Repairs.Count } else { $null }
            $presentation.Export($caseExport, 'PNG', 1280, 720)
            $pngs = Get-ChildItem -LiteralPath $caseExport -Filter *.png -File
            if ($slideCount -ne 3) {
                throw "$caseName opened with $slideCount slides instead of 3"
            }
            if ($editableTextCount -lt 6) {
                throw "$caseName exposed only $editableTextCount editable text shapes"
            }
            if ($pngs.Count -ne $slideCount) {
                throw "$caseName exported $($pngs.Count) PNG files for $slideCount slides"
            }
            if ($repairsSupported -and $repairCount -ne 0) {
                throw "$caseName reports $repairCount repairs"
            }
            $results += [ordered]@{
                case = $caseName
                opened = $true
                slideCount = $slideCount
                editableTextShapeCount = $editableTextCount
                pngExportCount = $pngs.Count
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
        checkedAt = '2026-08-16T00:00:00Z'
        application = $applicationInfo
        deckCount = $results.Count
        automatedOpenPassCount = @($results | Where-Object opened).Count
        repairPromptObservation = 'not-observable-in-suppressed-COM-run; human visible-window gate remains required'
        visualReviewStatus = 'ready_for_human_review'
        results = $results
    }
    $evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidencePath -Encoding utf8
    Write-Output "compatibility: $ApplicationName $($results.Count)/10 open, editable-text and PNG export checks passed"
}
finally {
    if ($null -ne $application) {
        try { $application.Quit() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
