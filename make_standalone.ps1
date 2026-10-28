# Regenerate the standalone (double-clickable) dashboard copy from the artifact-body build.
# Run after: .\.venv\Scripts\python.exe -m tankfloor dashboard
# The build output (data\processed\dashboard.html) is an artifact-body fragment with no
# doctype or charset; opened from disk it renders mojibake. This prepends the wrapper.
# Uses [IO.File] with BOM-less UTF-8 — PowerShell 5.1 Get-Content/Set-Content would
# double-encode the em-dashes silently. This script itself must stay pure ASCII:
# PS 5.1 reads BOM-less .ps1 files as ANSI and a literal em-dash breaks parsing.
$src = Join-Path $PSScriptRoot 'data\processed\dashboard.html'
$dst = Join-Path $PSScriptRoot 'TK201-Floor-Corrosion-Dashboard-2011-2026.html'
$enc = [Text.UTF8Encoding]::new($false)
$wrapper = "<!doctype html>`n<html lang=`"en`">`n<meta charset=`"utf-8`">`n<meta name=`"viewport`" content=`"width=device-width, initial-scale=1`">`n"
[IO.File]::WriteAllText($dst, $wrapper + [IO.File]::ReadAllText($src, $enc), $enc)
$delta = (Get-Item $dst).Length - (Get-Item $src).Length
if ($delta -ne $enc.GetByteCount($wrapper)) { throw "Delta $delta B != wrapper size - encoding drift, do not distribute." }
Write-Host "Wrote $dst ($((Get-Item $dst).Length) B, wrapper delta $delta B OK)"
