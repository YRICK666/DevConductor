[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern(
        '^(feature|fix|chore|docs|refactor|test)/[A-Za-z0-9._/-]+$'
    )]
    [string]$NewBranch,

    [string]$OldBranch
)

. "$PSScriptRoot\lib.ps1"

$RepoRoot = Get-RepoRoot
Push-Location $RepoRoot

try {
    Assert-CleanWorktree

    Write-Step "切换到 main"
    Invoke-Native `
        -FilePath "git" `
        -Arguments @("switch", "main")

    Write-Step "同步 main"
    Invoke-Native `
        -FilePath "git" `
        -Arguments @(
            "pull",
            "--ff-only",
            "origin",
            "main"
        )

    Invoke-Native `
        -FilePath "git" `
        -Arguments @("fetch", "--prune")

    if ($OldBranch) {
        if ($OldBranch -eq "main") {
            throw "不允许删除 main。"
        }

        & git show-ref `
            --verify `
            --quiet `
            "refs/heads/$OldBranch"

        if ($LASTEXITCODE -eq 0) {
            Write-Step "删除已合并的旧分支 $OldBranch"

            Invoke-Native `
                -FilePath "git" `
                -Arguments @("branch", "-d", $OldBranch)
        }
    }

    & git show-ref `
        --verify `
        --quiet `
        "refs/heads/$NewBranch"

    if ($LASTEXITCODE -eq 0) {
        Write-Step "切换到已有分支 $NewBranch"

        Invoke-Native `
            -FilePath "git" `
            -Arguments @("switch", $NewBranch)
    }
    else {
        Write-Step "创建分支 $NewBranch"

        Invoke-Native `
            -FilePath "git" `
            -Arguments @("switch", "-c", $NewBranch)
    }

    Write-Step "完成"
    git status
    git branch -vv
}
finally {
    Pop-Location
}
