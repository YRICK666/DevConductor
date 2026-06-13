. "$PSScriptRoot\lib.ps1"

$RepoRoot = Get-RepoRoot
Push-Location $RepoRoot

try {
    Write-Step "当前分支"
    git branch --show-current

    Write-Step "工作区状态"
    git status --short

    Write-Step "最近提交"
    git --no-pager log -5 --oneline --decorate

    Write-Step "分支跟踪"
    git --no-pager branch -vv

    Write-Step "Git worktree"
    git --no-pager worktree list
}
finally {
    Pop-Location
}
