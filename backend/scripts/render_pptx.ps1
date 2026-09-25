# Render every slide of a .pptx to PNG through PowerPoint, so the CPAG pack
# shown on screen is the downloadable file itself, page for page.
param([Parameter(Mandatory = $true)][string]$Deck,
      [Parameter(Mandatory = $true)][string]$OutDir,
      [int]$Width = 1600, [int]$Height = 900)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutDir | Out-Null
$pp = New-Object -ComObject PowerPoint.Application
try {
    # ReadOnly, Untitled, WithWindow=false
    $pres = $pp.Presentations.Open($Deck, $true, $false, $false)
    $n = $pres.Slides.Count
    for ($i = 1; $i -le $n; $i++) {
        $pres.Slides.Item($i).Export((Join-Path $OutDir ("s{0:D3}.png" -f $i)), "PNG", $Width, $Height)
    }
    $pres.Close()
    Write-Output $n
} finally {
    $pp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
