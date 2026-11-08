# Optional: download Olist via the Kaggle CLI (needs `pip install kaggle` and %USERPROFILE%\.kaggle\kaggle.json).
# Manual alternative: download the zip from Kaggle in the browser and extract into data\raw\olist\
$dest = "data\raw\olist"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
kaggle datasets download -d olistbr/brazilian-ecommerce -p $dest --unzip
Get-ChildItem $dest -Filter *.csv | Select-Object Name, Length
