param(
    [string]$Title,
    [string]$BodyFile,
    [string]$Head = "refactor/windows-app-modules-v2",
    [string]$Base = "main",
    [switch]$Draft
)

$ErrorActionPreference = "Stop"
$ExpectedRepo = "djebaz/Deep-Live-Cam-Remote"
$BlockedUpstreamRepo = "hacksider/Deep-Live-Cam"

$ResolvedRepo = (gh repo view --json nameWithOwner --jq .nameWithOwner).Trim()
if ($ResolvedRepo -eq $BlockedUpstreamRepo) {
    throw "Refusing to open a PR against upstream repository '$BlockedUpstreamRepo'. Use the downstream repo '$ExpectedRepo'."
}
if ($ResolvedRepo -ne $ExpectedRepo) {
    throw "Unexpected current GitHub repository '$ResolvedRepo'. Expected '$ExpectedRepo'."
}

$OriginUrl = (git remote get-url origin).Trim()
if ($OriginUrl -notmatch "djebaz[/\\:]Deep-Live-Cam-Remote(\.git)?$") {
    throw "Unexpected origin remote '$OriginUrl'. Expected '$ExpectedRepo'."
}
if ($OriginUrl -match "hacksider[/\\:]Deep-Live-Cam(\.git)?$") {
    throw "Refusing to open a PR from upstream origin '$OriginUrl'."
}

$Args = @(
    "pr", "create",
    "--repo", $ExpectedRepo,
    "--base", $Base,
    "--head", $Head
)

if ($Title) {
    $Args += @("--title", $Title)
}
if ($BodyFile) {
    $Args += @("--body-file", $BodyFile)
}
if ($Draft) {
    $Args += "--draft"
}

Write-Host "Repository guard OK: $ResolvedRepo"
Write-Host "Origin guard OK: $OriginUrl"
Write-Host "Running: gh $($Args -join ' ')"
& gh @Args
