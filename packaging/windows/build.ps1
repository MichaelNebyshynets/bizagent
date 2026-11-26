param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$repo = (Resolve-Path "$PSScriptRoot/../..").Path
$build = New-Item -ItemType Directory (Join-Path $env:RUNNER_TEMP "bizagent-build")
$stage = New-Item -ItemType Directory "$build/stage"
function Download($url, $name, $hash) {
    $path = Join-Path $build $name
    curl.exe -fLsS --retry 3 $url -o $path
    if ($hash -and (Get-FileHash $path).Hash -ne $hash) { throw "Checksum mismatch: $name" }
    return $path
}
$py = Download "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip" python.zip "608619F8619075629C9C69F361352A0DA6ED7E62F83A0E19C63E0EA32EB7629D"
Expand-Archive $py "$stage/python"
@("python310.zip",".","../bizagent","../","site-packages","import site") | Set-Content "$stage/python/python310._pth" -Encoding ascii
python -m pip install --only-binary :all: --target "$stage/python/site-packages" -r "$PSScriptRoot/requirements.lock"
$archive = Download "https://get.enterprisedb.com/postgresql/postgresql-18.6-1-windows-x64-binaries.zip" pg.zip ""
Expand-Archive $archive "$build/edb"
$env:PGROOT = "$stage/pgsql"
New-Item -ItemType Directory $env:PGROOT | Out-Null
$manifest = Get-Content "$PSScriptRoot/postgres-files.json" -Raw | ConvertFrom-Json -AsHashtable
foreach ($rel in $manifest.Keys) {
    $file = Join-Path "$build/edb/pgsql" $rel
    if ((Get-FileHash $file).Hash -ne $manifest[$rel]) { throw "Postgres checksum: $rel" }
    $dest = Join-Path $env:PGROOT $rel
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dest)) | Out-Null
    Copy-Item -LiteralPath $file -Destination $dest
}
Copy-Item "$build/edb/pgsql/include" $env:PGROOT -Recurse
Copy-Item "$build/edb/pgsql/*license*.txt" $env:PGROOT
git clone --branch v0.8.2 --depth 1 https://github.com/pgvector/pgvector.git "$build/vector"
Push-Location "$build/vector"
if ((git rev-parse HEAD) -ne "cab9da72c04353f143bb06b42ab70a403daac64a") { throw "pgvector revision" }
$vs = & "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe" -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
cmd /d /c "call `"$vs\VC\Auxiliary\Build\vcvars64.bat`" && nmake /f Makefile.win && nmake /f Makefile.win install"
Copy-Item LICENSE "$env:PGROOT/pgvector-LICENSE"
$crt = Get-ChildItem "$vs/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT" -Directory | Sort-Object FullName | Select-Object -Last 1
Copy-Item "$crt/*.dll" "$env:PGROOT/bin"
Pop-Location
Push-Location "$repo/biznes-frontend"
npm.cmd ci
npm.cmd run build
Copy-Item dist "$stage/frontend" -Recurse
Pop-Location
Copy-Item "$repo/bizagent" $stage -Recurse
Copy-Item "$repo/schema.sql","$PSScriptRoot/launcher.py" $stage
$compiler = Download "https://github.com/jrsoftware/issrc/releases/download/is-6_6_1/innosetup-6.6.1.exe" inno.exe "d243ce440c02705530699554fb9612b9b2bd7a2a90629cdb7f41e66f5faeb91f"
$p = Start-Process -Wait -PassThru -WindowStyle Hidden $compiler -ArgumentList "/VERYSILENT /PORTABLE=1 /NORESTART /DIR=`"$build/inno`""
if ($p.ExitCode) { throw "Inno Setup exit $($p.ExitCode)" }
New-Item -Force -ItemType Directory $Output | Out-Null
& "$build/inno/ISCC.exe" "/DStage=$stage" "/O$Output" "$PSScriptRoot/setup.iss"
((Get-FileHash "$Output/BizAgent-Setup.exe").Hash.ToLower() + "  BizAgent-Setup.exe") | Set-Content "$Output/BizAgent-Setup.exe.sha256" -Encoding ascii
