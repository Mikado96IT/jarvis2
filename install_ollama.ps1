$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$installer = Join-Path $PSScriptRoot "OllamaSetup.exe"
$url = "https://ollama.com/download/OllamaSetup.exe"

Write-Host "Download Ollama: $url"
Invoke-WebRequest -Uri $url -OutFile $installer

Write-Host "Avvio installer Ollama..."
Start-Process -FilePath $installer -Wait

Write-Host "Verifica Ollama..."
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    ollama --version
    Write-Host "Scarica il modello configurato:"
    Write-Host "ollama pull llama3.2"
} else {
    Write-Host "Ollama installato, ma CLI non ancora nel PATH. Riavvia il terminale o Windows."
}
