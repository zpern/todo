param(
    [string]$MainFile
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$build = Join-Path $project 'build'
New-Item -ItemType Directory -Path $build -Force | Out-Null

if ([string]::IsNullOrWhiteSpace($MainFile)) {
    $texFiles = @(Get-ChildItem -LiteralPath $project -File -Filter '*.tex' | Where-Object { $_.DirectoryName -eq $project })
    if ($texFiles.Count -eq 1) {
        $MainFile = $texFiles[0].Name
    } elseif ($texFiles.Count -eq 0) {
        throw 'No .tex file found in the project folder.'
    } else {
        $preferred = @($texFiles | Where-Object { $_.BaseName -in @('main', 'report', '论文') })
        if ($preferred.Count -eq 1) {
            $MainFile = $preferred[0].Name
        } else {
            $names = ($texFiles | ForEach-Object { $_.Name }) -join ', '
            throw "More than one top-level .tex file found: $names. Specify one with -MainFile, for example: .\build.ps1 -MainFile report.tex"
        }
    }
}

$mainPath = Join-Path $project $MainFile
if (-not (Test-Path -LiteralPath $mainPath -PathType Leaf)) {
    throw "Main TeX file not found: $MainFile"
}
if ([IO.Path]::GetExtension($mainPath) -ne '.tex') {
    throw 'MainFile must be a .tex file.'
}

Push-Location $project
try {
    & xelatex -interaction=nonstopmode -halt-on-error -synctex=1 '-output-directory=build' $MainFile
    if ($LASTEXITCODE -ne 0) { throw "XeLaTeX failed. See build\$([IO.Path]::GetFileNameWithoutExtension($MainFile)).log." }

    & xelatex -interaction=nonstopmode -halt-on-error -synctex=1 '-output-directory=build' $MainFile
    if ($LASTEXITCODE -ne 0) { throw "XeLaTeX second pass failed. See build\$([IO.Path]::GetFileNameWithoutExtension($MainFile)).log." }

    Write-Host "Build complete: build\$([IO.Path]::GetFileNameWithoutExtension($MainFile)).pdf"
} finally {
    Pop-Location
}
