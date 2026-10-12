param([switch]$Options)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonPath = [IO.Path]::GetFullPath($pythonPath)
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
}
$venvPython = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $pythonPath -m venv (Join-Path $projectPath '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed.' }
}
& $venvPython -m pip install --quiet webull-openapi-python-sdk==3.0.2
if ($LASTEXITCODE -ne 0) { throw 'Webull SDK installation failed.' }

$credentialNames = @('WEBULL_APP_KEY', 'WEBULL_APP_SECRET', 'WEBULL_SANDBOX_HOST')
$priorValues = @{}
foreach ($credentialName in $credentialNames) {
    $priorValues[$credentialName] = [Environment]::GetEnvironmentVariable($credentialName, 'Process')
}
try {
    Write-Host 'Enter SANDBOX paper credentials. Input is hidden and is not saved to a file.'
    foreach ($credentialName in @('WEBULL_APP_KEY', 'WEBULL_APP_SECRET')) {
        $privateValue = Read-Host $credentialName -AsSecureString
        $privatePointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($privateValue)
        try {
            [Environment]::SetEnvironmentVariable($credentialName,
                [Runtime.InteropServices.Marshal]::PtrToStringBSTR($privatePointer), 'Process')
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($privatePointer)
            $privateValue.Dispose()
        }
    }
    $env:WEBULL_SANDBOX_HOST = 'api.sandbox.webull.com'
    if ($Options) {
        & $venvPython (Join-Path $projectPath 'broker_check.py') interactive-preview
    } else {
        & $venvPython (Join-Path $projectPath 'broker_check.py') accounts
    }
    if ($LASTEXITCODE -ne 0) { throw 'Paper account check failed. No order was placed.' }
    Write-Host 'Check completed. No order was submitted; automatic trading is not enabled.'
} finally {
    foreach ($credentialName in $credentialNames) {
        [Environment]::SetEnvironmentVariable($credentialName, $priorValues[$credentialName], 'Process')
    }
}
