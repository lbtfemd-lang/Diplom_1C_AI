$base = 'd:\Share\Projects\diplom\Middleware'
Set-Location $base
$tmp = Join-Path $base '_pytest_tmp'
if (Test-Path $tmp) {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
$python = Join-Path $base '.venv\Scripts\python.exe'
$argsList = @('-m', 'pytest') + $args + @('--basetemp', $tmp, '-p', 'no:cacheprovider')
& $python @argsList
$code = $LASTEXITCODE
"EXIT: $code"
exit $code
