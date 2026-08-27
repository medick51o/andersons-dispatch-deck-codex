[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$InstallProfile
)

$ErrorActionPreference = "Stop"
$DeckRoot = Split-Path -Parent $PSScriptRoot
$CodexHomePath = if ($env:CODEX_HOME) {
    [IO.Path]::GetFullPath($env:CODEX_HOME)
} else {
    Join-Path $env:USERPROFILE ".codex"
}

$SkillTarget = Join-Path $CodexHomePath "skills\dispatch"
$AgentTarget = Join-Path $CodexHomePath "agents"
$DoctrineTarget = Join-Path $CodexHomePath "dispatch"

if ($PSCmdlet.ShouldProcess($CodexHomePath, "Install Codex Dispatch skill and agent profiles")) {
    New-Item -ItemType Directory -Force $SkillTarget, $AgentTarget, $DoctrineTarget | Out-Null
    Copy-Item -Recurse -Force (Join-Path $DeckRoot "skills\dispatch\*") $SkillTarget
    Copy-Item -Force (Join-Path $DeckRoot "agents\*.toml") $AgentTarget
    Copy-Item -Force (Join-Path $DeckRoot "SPINE.md") (Join-Path $DoctrineTarget "SPINE.md")
}

if ($InstallProfile) {
    $ProfileSource = Join-Path $DeckRoot "profile\AGENTS.md"
    $ProfileTarget = Join-Path $CodexHomePath "AGENTS.md"
    if (Test-Path -LiteralPath $ProfileTarget) {
        $SourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProfileSource).Hash
        $TargetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProfileTarget).Hash
        if ($SourceHash -ne $TargetHash) {
            $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $Backup = "$ProfileTarget.before-dispatch-$Stamp"
            if ($PSCmdlet.ShouldProcess($Backup, "Back up existing global Codex charter")) {
                Copy-Item -LiteralPath $ProfileTarget -Destination $Backup
                Write-Host "Backed up existing profile to $Backup"
            }
        }
    }
    if ($PSCmdlet.ShouldProcess($ProfileTarget, "Install global Codex conductor charter")) {
        Copy-Item -Force -LiteralPath $ProfileSource -Destination $ProfileTarget
    }
}

Write-Host "Installed Codex Dispatch into $CodexHomePath"
Write-Host "Restart Codex so the new skill and agent profiles are discovered."
