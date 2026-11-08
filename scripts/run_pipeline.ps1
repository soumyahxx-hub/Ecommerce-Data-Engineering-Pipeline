# Runs the full pipeline locally (venv active, docker compose postgres+rustfs up, .env present).
# Usage: .\scripts\run_pipeline.ps1 [-Until 2017-03-31] [-WindowDays 30]
param([string]$Until = "", [int]$WindowDays = 0)
$env:PYTHONPATH = "src"
$args_ = @("-m", "ecom_dw.pipeline", "run")
if ($Until) { $args_ += @("--until", $Until) }
if ($WindowDays -gt 0) { $args_ += @("--window-days", $WindowDays) }
python @args_
