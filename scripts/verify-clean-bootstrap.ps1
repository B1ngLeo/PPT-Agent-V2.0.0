$ErrorActionPreference = "Stop"

$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$temporaryRoot = Join-Path $repository ".tmp"
$target = Join-Path $temporaryRoot "g00-clean-bootstrap"
$expectedPrefix = $repository.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $target.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a temporary directory outside the repository: $target"
}
if ((Split-Path -Leaf $target) -ne "g00-clean-bootstrap") {
    throw "Unexpected clean-bootstrap directory: $target"
}

if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
New-Item -ItemType Directory -Path $target -Force | Out-Null

$excludedDirectories = @(
    ".git",
    ".tmp",
    ".next",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache"
)

try {
    & robocopy $repository $target /E /XD $excludedDirectories /XF ".env" "*.tsbuildinfo" | Out-Host
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }

    Push-Location $target
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "pnpm frozen install failed" }
        & python -m uv sync --frozen
        if ($LASTEXITCODE -ne 0) { throw "uv frozen sync failed" }
        & docker compose config --quiet
        if ($LASTEXITCODE -ne 0) { throw "Compose config validation failed" }
        & pnpm verify:contracts
        if ($LASTEXITCODE -ne 0) { throw "contract verification failed" }
        & pnpm verify:web
        if ($LASTEXITCODE -ne 0) { throw "Web verification failed" }
        & pnpm verify:api
        if ($LASTEXITCODE -ne 0) { throw "API verification failed" }
        & pnpm verify:worker
        if ($LASTEXITCODE -ne 0) { throw "Worker verification failed" }
        & pnpm verify:links
        if ($LASTEXITCODE -ne 0) { throw "Markdown link verification failed" }
        & pnpm verify:gates --goal G00
        if ($LASTEXITCODE -ne 0) { throw "G00 Gate verification failed" }
    }
    finally {
        Pop-Location
    }
}
finally {
    if (Test-Path -LiteralPath $target) {
        $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
        if (-not $resolvedTarget.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path -Leaf $resolvedTarget) -ne "g00-clean-bootstrap") {
            throw "Refusing to delete unexpected path: $resolvedTarget"
        }
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

Write-Output "G00 clean bootstrap and core verification passed."
