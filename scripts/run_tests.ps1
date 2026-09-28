<#
.SYNOPSIS
Run the Martin test suite with an explicitly selected project environment.

.DESCRIPTION
Set MARTIN_TEST_PYTHON to the project interpreter, or activate a Conda/virtual
environment first. There is no fallback to a system Python.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$testPython = if ($env:MARTIN_TEST_PYTHON) {
    $env:MARTIN_TEST_PYTHON
} elseif ($env:CONDA_PREFIX) {
    Join-Path $env:CONDA_PREFIX 'python.exe'
} elseif ($env:VIRTUAL_ENV) {
    Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
} else {
    throw 'Activate the project environment or set MARTIN_TEST_PYTHON.'
}

if (-not (Test-Path -LiteralPath $testPython -PathType Leaf)) {
    throw "Selected test Python was not found: $testPython"
}

if (-not $PytestArgs -or $PytestArgs.Count -eq 0) {
    $PytestArgs = @('tests')
}

Write-Host "Test Python: $testPython"
& $testPython -m pytest @PytestArgs
exit $LASTEXITCODE
