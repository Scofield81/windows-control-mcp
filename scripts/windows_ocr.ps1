param([Parameter(Mandatory=$true)][string]$Path)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Await-WinRT([object]$Operation, [type]$ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 } |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    return $task.GetAwaiter().GetResult()
}

$file = Await-WinRT ([Windows.Storage.StorageFile,Windows,ContentType=WindowsRuntime]::GetFileFromPathAsync((Resolve-Path $Path).Path)) ([Windows.Storage.StorageFile,Windows,ContentType=WindowsRuntime])
$stream = Await-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode,Windows,ContentType=WindowsRuntime]::Read)) ([Windows.Storage.Streams.IRandomAccessStream,Windows,ContentType=WindowsRuntime])
$decoder = Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder,Windows,ContentType=WindowsRuntime]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder,Windows,ContentType=WindowsRuntime])
$bitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap,Windows,ContentType=WindowsRuntime])
$language = [Windows.Globalization.Language,Windows,ContentType=WindowsRuntime]::new('hu')
$engine = [Windows.Media.Ocr.OcrEngine,Windows,ContentType=WindowsRuntime]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw 'The Hungarian Windows OCR engine is unavailable.' }
$result = Await-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult,Windows,ContentType=WindowsRuntime])
[ordered]@{
    language = 'hu'
    text = $result.Text
    lines = @($result.Lines | ForEach-Object { $_.Text })
} | ConvertTo-Json -Depth 5 -Compress
