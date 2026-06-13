[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Stage,

    [Parameter(Mandatory)]
    [string]$Goal,

    [string[]]$Scope = @(),

    [string[]]$Acceptance = @(),

    [string[]]$DoNot = @(),

    [string]$OutFile
)

. "$PSScriptRoot\lib.ps1"

$RepoRoot = Get-RepoRoot

if (-not $OutFile) {
    $SafeStage = $Stage -replace '[^\w.-]', '-'
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

    $OutFile = Join-Path `
        $RepoRoot `
        "prompts\$Timestamp-$SafeStage.md"
}

$ScopeText = if ($Scope.Count -gt 0) {
    ($Scope | ForEach-Object { "- $_" }) -join "`n"
}
else {
    "- 仅修改完成本任务所必需的文件"
}

$AcceptanceText = if ($Acceptance.Count -gt 0) {
    ($Acceptance | ForEach-Object { "- $_" }) -join "`n"
}
else {
    "- `.\scripts\verify.ps1 -SkipSync` 通过"
}

$DoNotText = if ($DoNot.Count -gt 0) {
    ($DoNot | ForEach-Object { "- $_" }) -join "`n"
}
else {
    @"
- 不实现下一阶段功能
- 不执行 git commit、merge 或 push
- 不读取或输出凭据
"@
}

$Content = @"
第一步完整读取并严格遵守仓库根目录的 AGENTS.md。

随后阅读 docs/PROJECT_CONTEXT.md，以及与本任务直接相关的代码和测试。
不要无目的扫描整个仓库，不要重复实现已有能力。

## 当前任务

阶段：$Stage

目标：

$Goal

## 范围

$ScopeText

## 验收标准

$AcceptanceText

## 不要做

$DoNotText

完成后实际运行：

- .\scripts\verify.ps1 -SkipSync
- git status --short
- git diff --stat
- git diff --check

不要创建提交或推送。

最终使用简体中文输出：

### 摘要
### 修改文件
### 验证
### 风险与下一步
"@

New-Item `
    -ItemType Directory `
    -Path (Split-Path $OutFile) `
    -Force |
    Out-Null

Set-Content `
    -Path $OutFile `
    -Value $Content `
    -Encoding UTF8

Write-Host "已生成：$OutFile" -ForegroundColor Green
