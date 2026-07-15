$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
foreach ($name in @("build", "dist")) {
    $target = [IO.Path]::GetFullPath((Join-Path $root $name))
    if ([IO.Path]::GetDirectoryName($target) -ne $root) {
        throw "Refusing to clean a path outside the FuelOpt workspace: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Write-Host "FuelOpt release artifacts cleaned under $root"
