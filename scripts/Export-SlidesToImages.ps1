<#
.SYNOPSIS
    Export PowerPoint slides to individual PNG images using COM automation.

.DESCRIPTION
    Uses PowerPoint's COM automation (Slide.Export / Presentation.Export) to
    render each slide as a PNG image at the specified resolution. Requires
    Microsoft PowerPoint to be installed on the machine.

    Reference: https://gist.github.com/ap0llo/5c5f5aadb885fe918000b248e5dd6e36

.PARAMETER PptxPath
    Path to the .pptx file to export.

.PARAMETER OutDir
    Directory where slide images will be saved. Created if it does not exist.

.PARAMETER Width
    Image width in pixels (default: 1920).

.PARAMETER Height
    Image height in pixels (default: 1080).

.EXAMPLE
    .\Export-SlidesToImages.ps1 -PptxPath deck.pptx -OutDir images\deck

.EXAMPLE
    .\Export-SlidesToImages.ps1 -PptxPath deck.pptx -OutDir images\deck -Width 2560 -Height 1440
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$PptxPath,

    [Parameter(Mandatory=$true)]
    [string]$OutDir,

    [int]$Width  = 1920,
    [int]$Height = 1080
)

# Validate input file
if (-not (Test-Path $PptxPath)) {
    Write-Error "File not found: $PptxPath"
    exit 1
}

# Resolve to absolute path (COM requires it).
# Use .ProviderPath instead of .Path to avoid the
# "Microsoft.PowerShell.Core\FileSystem::" prefix that
# PowerShell adds to UNC/WSL paths — COM can't parse it.
$PptxPath = (Resolve-Path $PptxPath).ProviderPath

# Ensure output directory exists
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$OutDir = (Resolve-Path $OutDir).ProviderPath

Write-Host "Exporting slides from: $PptxPath"
Write-Host "Output directory:      $OutDir"
Write-Host "Resolution:            ${Width}x${Height}"

$pp = New-Object -ComObject PowerPoint.Application

# Try to hide the PowerPoint window; some Office configurations disallow this
try {
    $pp.Visible = 0  # msoFalse
} catch {
    # Non-fatal — PowerPoint will remain visible during export
}

$presentation = $null

try {
    $presentation = $pp.Presentations.Open(
        $PptxPath,
        -1,  # msoTrue  — ReadOnly
         0,  # msoFalse — Untitled
         0   # msoFalse — WithWindow
    )

    $slideCount = $presentation.Slides.Count
    Write-Host "Found $slideCount slide(s)"

    # Export entire presentation — PowerPoint creates Slide1.png, Slide2.png, etc.
    $presentation.Export($OutDir, "PNG", $Width, $Height)

    Write-Host "Exported $slideCount slide(s) to: $OutDir"

    $presentation.Close()
}
catch {
    Write-Error "Export failed: $_"
    exit 1
}
finally {
    $pp.Quit() | Out-Null

    # Clean up COM references to avoid orphaned POWERPNT.EXE
    if ($presentation) {
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) | Out-Null
    }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
