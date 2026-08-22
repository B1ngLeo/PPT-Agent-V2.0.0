param(
    [string]$OutputRoot = "docs/evidence/issue003/baseline"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedOutput = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $OutputRoot))
$expectedParent = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "docs\evidence\issue003"))
if (-not $resolvedOutput.StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must remain inside docs/evidence/issue003"
}
[void](New-Item -ItemType Directory -Path $resolvedOutput -Force)

$snapshotQuery = @"
SELECT jsonb_pretty(
  jsonb_build_object(
    'jobId', j.id,
    'jobStatus', j.status,
    'snapshotId', s.id,
    'snapshotSha256', s.snapshot_sha256,
    'intentRevisionId', s.intent_revision_id,
    'outlineRevisionId', s.outline_revision_id,
    'approvalId', s.approval_id,
    'payload', s.payload
  )
)
FROM generation_jobs j
JOIN generation_snapshots s ON s.id = j.snapshot_id
WHERE j.id = '01M0KZ2JRRW8PJKER5KVVXFTMF';
"@
$snapshotJson = docker compose exec -T postgres psql -U instant_ppt -d instant_ppt `
    -X -q -t -A -c $snapshotQuery
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($snapshotJson -join "`n"))) {
    throw "The frozen before snapshot could not be recovered from PostgreSQL"
}
$snapshotPath = Join-Path $resolvedOutput "before-approved-snapshot.json"
($snapshotJson -join "`n").Trim() | Set-Content -LiteralPath $snapshotPath -Encoding utf8

$minioContainer = (docker compose ps -q minio).Trim()
if ([string]::IsNullOrWhiteSpace($minioContainer)) {
    throw "The Compose MinIO container is not running"
}
$objects = @(
    [ordered]@{
        Key = "tenants/01M0D9MESSTSY6C63QA9AGM8T1/published/01G53VJ2CDFXTCFHXND438NY21"
        Name = "before-deterministic-template.pptx"
        Sha256 = "4fa9901f9c4a38c2d41fd98e60cd65c56999caa4050be4c8f37cb73aeba4fe6e"
    },
    [ordered]@{
        Key = "tenants/01M0D9MESSTSY6C63QA9AGM8T1/published/01M0KT5WF515DVFW7MJ7HW7532"
        Name = "before-approved-source.md"
        Sha256 = "811333418f1cf5b69330c0812781a82fa89467a403049c51e211653656ee04cf"
    },
    [ordered]@{
        Key = "tenants/01M0D9MESSTSY6C63QA9AGM8T1/published/01M0KT5WF515DVFW7MJ7HW7533"
        Name = "before-conversion-profile.json"
        Sha256 = "4818925561b4732a3f0ed7bca05791b789c59a6b27d8dc4a98c8ab31ed0fb857"
    }
)
foreach ($object in $objects) {
    $temporaryPath = "/tmp/issue003-$($object.Name)"
    $copyCommand = @"
mc --config-dir /tmp/issue003-mc alias set issue003 http://127.0.0.1:9000 "`$MINIO_ROOT_USER" "`$MINIO_ROOT_PASSWORD" >/dev/null && mc --config-dir /tmp/issue003-mc cp "issue003/instant-ppt-private/$($object.Key)" "$temporaryPath" >/dev/null
"@
    docker compose exec -T minio sh -c $copyCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to recover $($object.Name) from private object storage"
    }
    $target = Join-Path $resolvedOutput $object.Name
    docker cp "${minioContainer}:${temporaryPath}" $target | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy $($object.Name) out of the MinIO container"
    }
    docker compose exec -T minio rm -f $temporaryPath | Out-Null
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
    if ($actual -ne $object.Sha256) {
        throw "$($object.Name) hash mismatch: expected $($object.Sha256), got $actual"
    }
}

$referenceCandidates = @(
    Get-ChildItem -LiteralPath (Join-Path $repositoryRoot "projects") -Directory |
        Where-Object { $_.Name.EndsWith("_ppt169_20260816") }
)
if ($referenceCandidates.Count -ne 1) {
    throw "Expected one reference project ending in _ppt169_20260816"
}
$referenceProject = $referenceCandidates[0].FullName
$referencePptxCandidates = @(
    Get-ChildItem -LiteralPath (Join-Path $referenceProject "exports") -Filter "*20260816_235825.pptx" -File
)
$referenceSourceCandidates = @(
    Get-ChildItem -LiteralPath (Join-Path $referenceProject "sources") -Filter "*.md" -File
)
if ($referencePptxCandidates.Count -ne 1 -or $referenceSourceCandidates.Count -ne 1) {
    throw "Reference project must expose one frozen PPTX and one Markdown source"
}
$referencePptx = $referencePptxCandidates[0].FullName
$referenceSource = $referenceSourceCandidates[0].FullName
foreach ($source in @($referencePptx, $referenceSource)) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Reference baseline input is missing: $source"
    }
}
Copy-Item -LiteralPath $referencePptx `
    -Destination (Join-Path $resolvedOutput "reference-ppt-master.pptx") -Force
Copy-Item -LiteralPath $referenceSource `
    -Destination (Join-Path $resolvedOutput "reference-source-recovered.md") -Force
Copy-Item -LiteralPath (Join-Path $referenceProject "design_spec.md") `
    -Destination (Join-Path $resolvedOutput "reference-design-spec.md") -Force
Copy-Item -LiteralPath (Join-Path $referenceProject "spec_lock.md") `
    -Destination (Join-Path $resolvedOutput "reference-spec-lock.md") -Force

$downloadCandidates = @(
    Get-ChildItem -LiteralPath "E:\" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Filter "GPT 5.6 *.pptx" -File -ErrorAction SilentlyContinue
        } |
        Where-Object { $_.Length -eq 51883 }
)
if ($downloadCandidates.Count -eq 1) {
    Copy-Item -LiteralPath $downloadCandidates[0].FullName `
        -Destination (Join-Path $resolvedOutput "before-user-download.pptx") -Force
}

Write-Output "ISSUE-003 baseline inputs frozen at $resolvedOutput"
