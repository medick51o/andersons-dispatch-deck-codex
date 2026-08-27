[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$RemoveProfile
)

$ErrorActionPreference = "Stop"
$DeckRoot = Split-Path -Parent $PSScriptRoot
$CodexHomePath = if ($env:CODEX_HOME) {
    [IO.Path]::GetFullPath($env:CODEX_HOME)
} else {
    Join-Path $env:USERPROFILE ".codex"
}
$CodexHomeResolved = [IO.Path]::GetFullPath($CodexHomePath).TrimEnd('\', '/')

function Assert-CodexChild([string]$Path) {
    $Resolved = [IO.Path]::GetFullPath($Path)
    $Prefix = $CodexHomeResolved + [IO.Path]::DirectorySeparatorChar
    if (-not $Resolved.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside Codex home: $Resolved"
    }
    return $Resolved
}

$Targets = @(
    (Join-Path $CodexHomePath "skills\dispatch"),
    (Join-Path $CodexHomePath "agents\dispatch-explorer.toml"),
    (Join-Path $CodexHomePath "agents\dispatch-reviewer.toml"),
    (Join-Path $CodexHomePath "dispatch\SPINE.md")
)

foreach ($Target in $Targets) {
    $SafeTarget = Assert-CodexChild $Target
    if ((Test-Path -LiteralPath $SafeTarget) -and
        $PSCmdlet.ShouldProcess($SafeTarget, "Remove Codex Dispatch installed file")) {
        Remove-Item -Recurse -Force -LiteralPath $SafeTarget
    }
}

if ($RemoveProfile) {
    $ProfileSource = Join-Path $DeckRoot "profile\AGENTS.md"
    $ProfileTarget = Assert-CodexChild (Join-Path $CodexHomePath "AGENTS.md")
    if ((Test-Path -LiteralPath $ProfileSource) -and (Test-Path -LiteralPath $ProfileTarget)) {
        $SourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProfileSource).Hash
        $TargetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProfileTarget).Hash
        if ($SourceHash -eq $TargetHash) {
            if ($PSCmdlet.ShouldProcess($ProfileTarget, "Remove matching Codex conductor charter")) {
                Remove-Item -Force -LiteralPath $ProfileTarget
            }
        } else {
            Write-Warning "Global AGENTS.md was modified; leaving it in place."
        }
    }
}

Write-Host "Removed tracked Codex Dispatch installation files."
Write-Host "MCP registrations and timestamped profile backups were left untouched."
