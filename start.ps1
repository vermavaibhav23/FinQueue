$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:DJANGO_SETTINGS_MODULE = 'finqueue.test_settings'

Write-Host 'Applying database migrations...'
python .\manage.py migrate

Write-Host 'Starting Django development server on http://127.0.0.1:8000'
python .\manage.py runserver 0.0.0.0:8000
