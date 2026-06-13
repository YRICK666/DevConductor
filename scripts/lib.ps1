Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Native {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    $ExitCode = $LASTEXITCODE

    if ($ExitCode -ne 0) {
        $RenderedArguments = $Arguments -join " "
        throw "$FilePath 运行失败，退出码 ${ExitCode}：$RenderedArguments"
    }
}

function Get-RepoRoot {
    $Root = & git rev-parse --show-toplevel 2>$null

    if ($LASTEXITCODE -ne 0 -or -not $Root) {
        throw "当前目录不在 Git 仓库中。"
    }

    return [System.IO.Path]::GetFullPath(
        ($Root | Select-Object -First 1).Trim()
    )
}

function Assert-CleanWorktree {
    $Status = @(
        & git status --porcelain=v1 --untracked-files=all
    )

    if ($LASTEXITCODE -ne 0) {
        throw "无法读取 Git 工作区状态。"
    }

    if ($Status.Count -gt 0) {
        $Status | ForEach-Object { Write-Host $_ }
        throw "工作区存在未提交修改，操作已停止。"
    }
}

function Write-Step {
    param([string]$Message)

    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}
