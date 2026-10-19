# MyAgentKit_Keel — the PowerShell front door, a thin shim over install.sh. The kit runs on
# Git for Windows' sh like everywhere else; this finds that sh and hands it install.sh and the
# arguments, from the current directory (the project root).
#
#   irm https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.ps1 | iex
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.ps1))) --overlay claude-code
#   & ([scriptblock]::Create((irm .../install.ps1))) sync
#
# MYAGENTKIT_REF and MYAGENTKIT_REPO pass through to install.sh through the environment.
# One child scope: iex runs in the caller's, and left its variables in the owner's session.
& {
    # Git's own bin\sh.exe, the one that puts Git's usr\bin ahead of System32 on PATH: a bare
    # usr\bin\sh.exe behind System32 ran the kit with Windows' FIND.EXE for find. First the Git
    # of the git on PATH (Git\cmd, Git\bin or Git\mingw64\bin), then the default folder, then
    # any sh on PATH.
    $candidates = @()
    $git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($git) {
        $bin = Split-Path $git.Source
        $candidates += (Join-Path $bin 'sh.exe'), (Join-Path (Split-Path $bin) 'bin\sh.exe'),
            (Join-Path (Split-Path (Split-Path $bin)) 'bin\sh.exe')
    }
    if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles 'Git\bin\sh.exe' }
    $found = Get-Command sh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $candidates += $found.Source }
    $sh = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $sh) {
        throw 'install: no sh found. The kit needs Git for Windows (https://git-scm.com/download/win), which ships sh; install it and rerun. Nothing was changed.'
    }

    # Run from a clone: the install.sh beside this file. Run through irm | iex: the published one.
    $local = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'install.sh' }
    if ($local -and (Test-Path -LiteralPath $local)) {
        $text = [IO.File]::ReadAllText($local)
    } else {
        try {
            $text = Invoke-RestMethod 'https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh' -ErrorAction Stop
        } catch {
            throw "install: cannot download install.sh (no network?): $($_.Exception.Message). Nothing was changed."
        }
    }
    # The arguments ride in the script, single-quoted for sh, never on sh's command line:
    # Windows PowerShell 5.1 hands a native program an argument with quotes and spaces in pieces.
    $set = 'set --' + -join ($args | ForEach-Object { " '" + ([string]$_).Replace("'", "'\''") + "'" })
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ('myagentkit-install-' + [guid]::NewGuid() + '.sh')
    [IO.File]::WriteAllText($temporary, $set + "`n" + $text.Replace("`r`n", "`n"))
    try {
        & $sh $temporary
        $code = $LASTEXITCODE
    } finally {
        Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
    }
    # exit only when run as a file: under iex it would close the owner's PowerShell window.
    if ($PSCommandPath) { exit $code }
    $global:LASTEXITCODE = $code
} @args
