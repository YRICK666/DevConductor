param(
    [string]$ProjectRoot = "G:\AI-Workstation\dev-conductor"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (Test-Path $ProjectRoot) {
    $existingItems = @(Get-ChildItem -LiteralPath $ProjectRoot -Force -ErrorAction SilentlyContinue)
    if ($existingItems.Count -gt 0) {
        throw "Target directory already exists and is not empty: $ProjectRoot"
    }
} else {
    New-Item -ItemType Directory -Path $ProjectRoot -Force | Out-Null
}

$directories = @(
    "backend\app",
    "backend\tests",
    "docs",
    "frontend",
    "tasks",
    "runs"
)

foreach ($directory in $directories) {
    New-Item -ItemType Directory -Path (Join-Path $ProjectRoot $directory) -Force | Out-Null
}

$filesToCopy = @(
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    ".gitignore",
    "docs\ARCHITECTURE.md",
    "docs\DECISIONS.md",
    "backend\app\.gitkeep",
    "backend\tests\.gitkeep",
    "frontend\.gitkeep",
    "tasks\.gitkeep",
    "runs\.gitkeep"
)

foreach ($relativePath in $filesToCopy) {
    $source = Join-Path $sourceRoot $relativePath
    $destination = Join-Path $ProjectRoot $relativePath
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

Push-Location $ProjectRoot
try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git was not found in PATH."
    }

    if (-not (Test-Path ".git")) {
        git init
        if ($LASTEXITCODE -ne 0) {
            throw "git init failed with exit code $LASTEXITCODE"
        }
    }

    Write-Host ""
    Write-Host "DevConductor project created at:" -ForegroundColor Green
    Write-Host "  $ProjectRoot"
    Write-Host ""
    Write-Host "Review the files, then create the initial commit with:"
    Write-Host '  git add .'
    Write-Host '  git commit -m "chore: bootstrap DevConductor repository"'
    Write-Host ""
    Write-Host "Verify Codex instructions with:"
    Write-Host '  codex --ask-for-approval never "Summarize the repository instructions and current milestone. Do not modify files."'
} finally {
    Pop-Location
}

