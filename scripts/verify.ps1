[CmdletBinding()]
param(
    [switch]$SkipSync
)

. "$PSScriptRoot\lib.ps1"

$RepoRoot = Get-RepoRoot
Push-Location $RepoRoot

try {
    Write-Step "检查依赖环境"

    if (-not $SkipSync) {
        Invoke-Native `
            -FilePath "uv" `
            -Arguments @("sync", "--dev", "--locked")
    }

    Write-Step "运行 pytest"
    Invoke-Native `
        -FilePath "uv" `
        -Arguments @("run", "--frozen", "pytest")

    Write-Step "运行 Ruff"
    Invoke-Native `
        -FilePath "uv" `
        -Arguments @("run", "--frozen", "ruff", "check", ".")

    Write-Step "运行 mypy"
    Invoke-Native `
        -FilePath "uv" `
        -Arguments @("run", "--frozen", "mypy", "backend")

    Write-Step "检查 Git 空白错误"
    Invoke-Native `
        -FilePath "git" `
        -Arguments @("diff", "--check")

    Invoke-Native `
        -FilePath "git" `
        -Arguments @("diff", "--cached", "--check")

    Write-Step "检查不应提交的文件"

    $Status = @(
        & git status --porcelain=v1 --untracked-files=all
    )

    if ($LASTEXITCODE -ne 0) {
        throw "无法读取 Git 状态。"
    }

    $ForbiddenPaths = @(
        $Status | Where-Object {
            $_ -match '(^|\s)(\.env(?:\.|$)|\.venv/|\.tmp/|[^/]+\.egg-info/)'
        }
    )

    if ($ForbiddenPaths.Count -gt 0) {
        $ForbiddenPaths | ForEach-Object {
            Write-Host $_ -ForegroundColor Red
        }

        throw "发现不应提交的临时文件或敏感配置。"
    }

    Write-Step "扫描应用代码中的高风险调用"

    $ApplicationFiles = @()

    if (Test-Path ".\backend\app") {
        $ApplicationFiles = @(
            Get-ChildItem `
                ".\backend\app" `
                -Recurse `
                -File `
                -Filter "*.py"
        )
    }

    $DangerousPatterns = @(
        'shell\s*=\s*True',
        'create_subprocess_shell',
        'subprocess\.(run|Popen|call|check_call|check_output)'
    )

    $DangerousMatches = @(
        $ApplicationFiles |
            Select-String -Pattern $DangerousPatterns
    )

    if ($DangerousMatches.Count -gt 0) {
        $DangerousMatches | ForEach-Object {
            Write-Host $_ -ForegroundColor Red
        }

        throw "发现绕过 CommandRunner 的进程调用。"
    }

    Write-Step "扫描常见密钥格式"

    $SourceFiles = @()

    foreach ($Directory in @(
        ".\backend",
        ".\scripts",
        ".\tasks",
        ".\docs"
    )) {
        if (Test-Path $Directory) {
            $SourceFiles += Get-ChildItem `
                $Directory `
                -Recurse `
                -File |
                Where-Object {
                    $_.Extension -in @(
                        ".py",
                        ".ps1",
                        ".toml",
                        ".yaml",
                        ".yml",
                        ".json",
                        ".md"
                    )
                }
        }
    }

    $SecretPatterns = @(
        'sk-[A-Za-z0-9_-]{20,}',
        'ghp_[A-Za-z0-9]{20,}',
        'AKIA[0-9A-Z]{16}',
        '-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----'
    )

    $SecretMatches = @(
        $SourceFiles |
            Select-String -Pattern $SecretPatterns
    )

    if ($SecretMatches.Count -gt 0) {
        $SecretMatches | ForEach-Object {
            Write-Host $_ -ForegroundColor Red
        }

        throw "发现疑似密钥内容，请人工检查。"
    }

    Write-Step "验证完成"
    git status --short

    Write-Host ""
    Write-Host "全部检查通过。" -ForegroundColor Green
}
finally {
    Pop-Location
}
