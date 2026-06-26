param(
    [string]$Repo = "djebaz/Deep-Live-Cam-Remote"
)

$ErrorActionPreference = "Stop"
$ExpectedRepo = "djebaz/Deep-Live-Cam-Remote"
$BlockedUpstreamRepo = "hacksider/Deep-Live-Cam"

$ResolvedRepo = (gh repo view $Repo --json nameWithOwner --jq .nameWithOwner).Trim()

if ($ResolvedRepo -eq $BlockedUpstreamRepo) {
    throw "Refusing to open a PR against upstream repository '$BlockedUpstreamRepo'. Use --repo $ExpectedRepo."
}

if ($ResolvedRepo -ne $ExpectedRepo) {
    throw "Unexpected GitHub repository '$ResolvedRepo'. Expected '$ExpectedRepo'. Use --repo $ExpectedRepo."
}

Write-Host "Repository guard OK: $ResolvedRepo"
Write-Host "Use explicit GitHub CLI repository arguments, for example:"
Write-Host "gh pr create --repo $ExpectedRepo --base main --head refactor/windows-app-modules-v2"
