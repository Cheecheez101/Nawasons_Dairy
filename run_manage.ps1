param([Parameter(ValueFromRemainingArguments=$true)][String[]]$Args)
$venv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $venv "$PSScriptRoot\manage.py" @Args
