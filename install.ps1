# MyAgentKit_Keel — the PowerShell front door, a thin shim over install.sh. The kit runs on
# Git for Windows' sh like everywhere else; this finds that sh and hands it install.sh and the
# arguments, from the current directory (the project root).
#
#   irm https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.ps1 | iex
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.ps1))) --overlay claude-code
#   & ([scriptblock]::Create((irm .../install.ps1))) sync
#
# MYAGENTKIT_REF and MYAGENTKIT_REPO pass through to install.sh through the environment.
$ErrorActionPreference = 'Stop'

# sh on PATH, else the sh of the Git on PATH (Git\cmd\git.exe or Git\mingw64\bin\git.exe beside
# Git\bin\sh.exe), else the default Git for Windows folder.
$candidates = @()
$found = Get-Command sh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($found) { $candidates += $found.Source }
$git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($git) {
    $gitDir = Split-Path (Split-Path $git.Source)
    $candidates += (Join-Path $gitDir 'bin\sh.exe'), (Join-Path (Split-Path $gitDir) 'bin\sh.exe')
}
if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles 'Git\bin\sh.exe' }
$sh = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $sh) {
    throw 'install: no sh found. The kit needs Git for Windows (https://git-scm.com/download/win), which ships sh; install it and rerun. Nothing was changed.'
}

# Run from a clone: the install.sh beside this file. Run through irm | iex: the published one.
$script = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'install.sh' } else { $null }
$temporary = $null
if (-not $script -or -not (Test-Path -LiteralPath $script)) {
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ('myagentkit-install-' + [guid]::NewGuid() + '.sh')
    try {
        $text = Invoke-RestMethod 'https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh'
    } catch {
        throw "install: cannot download install.sh (no network?): $($_.Exception.Message). Nothing was changed."
    }
    [IO.File]::WriteAllText($temporary, $text.Replace("`r`n", "`n"))
    $script = $temporary
}
try {
    & $sh $script @args
    $code = $LASTEXITCODE
} finally {
    if ($temporary) { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
}
# exit only when run as a file: under iex it would close the owner's PowerShell window.
if ($PSCommandPath) { exit $code }
$global:LASTEXITCODE = $code
