<#
.SYNOPSIS
Run the Martin test suite with the project's permanent Conda test environment.

.DESCRIPTION
By default this script uses E:\conda\envs\monai_learning\python.exe.
Set MARTIN_TEST_PYTHON when a different machine stores the same environment at
another path. Any remaining arguments are passed directly to pytest.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$defaultPython = 'E:\conda\envs\monai_learning\python.exe'
$python = if ($env:MARTIN_TEST_PYTHON) { $env:MARTIN_TEST_PYTHON } else { $defaultPython }

if (-not (Test-Path -LiteralPath $python)) {
    throw "Test Python was not found: $python. Install monai_learning or set MARTIN_TEST_PYTHON."
}

if (-not $PytestArgs -or $PytestArgs.Count -eq 0) {
    $PytestArgs = @('tests')
}

& $python -m pytest @PytestArgs
exit $LASTEXITCODE
