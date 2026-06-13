[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$CommitMessage,

    [string[]]$Paths,

    [switch]$All,

    [switch]$SkipSync,

    [switch]$Push,

    [switch]$CreatePr,

    [string]$PrTitle,

    [string]$PrBody,

    [switch]$Yes
)

. "$PSScriptRoot\lib.ps1"

$RepoRoot = Get-RepoRoot
Push-Location $RepoRoot

try {
    $Branch = (
        & git branch --show-current
    ).Trim()

    if ($LASTEXITCODE -ne 0 -or -not $Branch) {
        throw "无法读取当前分支。"
    }

    if ($Branch -eq "main") {
        throw "不允许直接在 main 上完成阶段提交。"
    }

    Write-Step "运行完整验证"

    if ($SkipSync) {
        & "$PSScriptRoot\verify.ps1" -SkipSync
    }
    else {
        & "$PSScriptRoot\verify.ps1"
    }

    Write-Step "暂存文件"

    if ($All) {
        Invoke-Native `
            -FilePath "git" `
            -Arguments @("add", "-A")
    }
    elseif ($Paths -and $Paths.Count -gt 0) {
        $GitArguments = @("add", "--") + $Paths

        Invoke-Native `
            -FilePath "git" `
            -Arguments $GitArguments
    }
    else {
        throw "请指定 -All，或使用 -Paths 明确列出文件。"
    }

    Invoke-Native `
        -FilePath "git" `
        -Arguments @("diff", "--cached", "--check")

    & git diff --cached --quiet
    $DiffExitCode = $LASTEXITCODE

    if ($DiffExitCode -eq 0) {
        throw "暂存区没有可提交的改动。"
    }

    if ($DiffExitCode -ne 1) {
        throw "无法读取暂存区改动。"
    }

    Write-Step "待提交改动"
    git diff --cached --stat
    git status --short

    if (-not $Yes) {
        $Answer = Read-Host "确认提交以上改动？[y/N]"

        if ($Answer -notin @("y", "Y")) {
            throw "用户取消提交。"
        }
    }

    Write-Step "创建提交"

    Invoke-Native `
        -FilePath "git" `
        -Arguments @(
            "commit",
            "-m",
            $CommitMessage
        )

    if ($Push -or $CreatePr) {
        Write-Step "推送功能分支"

        Invoke-Native `
            -FilePath "git" `
            -Arguments @(
                "push",
                "-u",
                "origin",
                $Branch
            )
    }

    if ($CreatePr) {
        if (-not $PrTitle) {
            $PrTitle = $CommitMessage
        }

        if (-not $PrBody) {
            $PrBody = @"
## Summary

$CommitMessage

## Verification

- pytest
- Ruff
- mypy
- git diff --check

## Safety

- No automatic merge
- No automatic acceptance
- Human review required
"@
        }

        $Gh = Get-Command "gh" -ErrorAction SilentlyContinue

        if ($Gh) {
            Write-Step "创建 Pull Request"

            & gh pr create `
                --base "main" `
                --head $Branch `
                --title $PrTitle `
                --body $PrBody

            if ($LASTEXITCODE -ne 0) {
                Write-Warning "gh 创建 PR 失败，将改为打开网页。"
                $Gh = $null
            }
        }

        if (-not $Gh) {
            $Remote = (
                & git remote get-url origin
            ).Trim()

            if ($LASTEXITCODE -ne 0) {
                throw "无法读取 origin 地址。"
            }

            $Repository = $Remote `
                -replace '^https://github\.com/', '' `
                -replace '^git@github\.com:', '' `
                -replace '\.git$', ''

            $Url = "https://github.com/$Repository/pull/new/$Branch"

            Write-Host "PR 地址：$Url"
            Start-Process $Url
        }
    }

    Write-Step "阶段提交完成"
    git status
    git log -3 --oneline
}
finally {
    Pop-Location
}
