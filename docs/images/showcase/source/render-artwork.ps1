param([string]$Repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..')))
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$artRoot = $PSScriptRoot
$artOutput = Join-Path $Repository 'docs\images\showcase'
[IO.Directory]::CreateDirectory($artOutput) | Out-Null
$artRows = Get-Content -LiteralPath (Join-Path $artRoot 'artwork.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$artBackground = [Drawing.Image]::FromFile((Join-Path $artRoot 'brand-background.jpg'))
$jpegEncoder = [Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object MimeType -eq 'image/jpeg'
$jpegParams = [Drawing.Imaging.EncoderParameters]::new(1)
$jpegParams.Param[0] = [Drawing.Imaging.EncoderParameter]::new([Drawing.Imaging.Encoder]::Quality, [long]94)
function Brush([string]$hex) { return [Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($hex)) }
function Text([string]$s,[single]$x,[single]$y,[single]$size,[string]$color='#f3f1e9',[bool]$bold=$false) {
 $font = [Drawing.Font]::new('Segoe UI', $size, $(if($bold){[Drawing.FontStyle]::Bold}else{[Drawing.FontStyle]::Regular}), [Drawing.GraphicsUnit]::Pixel)
 $brush = Brush $color
 try {$graphics.DrawString($s,$font,$brush,$x,$y,[Drawing.StringFormat]::GenericTypographic)} finally {$font.Dispose();$brush.Dispose()}
}
function Rect([single]$x,[single]$y,[single]$w,[single]$h,[string]$color){$b=Brush $color;try{$graphics.FillRectangle($b,$x,$y,$w,$h)}finally{$b.Dispose()}}
function Logo([single]$x,[single]$y,[single]$scale=1) {
 $a=[Drawing.PointF[]]@([Drawing.PointF]::new($x+10*$scale,$y+1*$scale),[Drawing.PointF]::new($x+21*$scale,$y+1*$scale),[Drawing.PointF]::new($x+12*$scale,$y+31*$scale),[Drawing.PointF]::new($x+1*$scale,$y+31*$scale))
 $b=[Drawing.PointF[]]@([Drawing.PointF]::new($x+27*$scale,$y+1*$scale),[Drawing.PointF]::new($x+38*$scale,$y+1*$scale),[Drawing.PointF]::new($x+29*$scale,$y+31*$scale),[Drawing.PointF]::new($x+18*$scale,$y+31*$scale))
 $brush=Brush '#1bd9ce';$graphics.FillPolygon($brush,$a);$brush.Dispose();$brush=Brush '#a38bd0';$graphics.FillPolygon($brush,$b);$brush.Dispose()
}
foreach ($row in $artRows) {
 $bitmap = [Drawing.Bitmap]::new(1600,900)
 $graphics = [Drawing.Graphics]::FromImage($bitmap)
 $graphics.SmoothingMode = 'AntiAlias';$graphics.InterpolationMode='HighQualityBicubic';$graphics.PixelOffsetMode='HighQuality';$graphics.TextRenderingHint='AntiAliasGridFit'
 try {
  $graphics.DrawImage($artBackground,0,0,1600,900)
  $veil=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(110,10,17,20));$graphics.FillRectangle($veil,0,0,1600,900);$veil.Dispose()
  Logo 64 56
  Text 'CUTROOM' 116 49 31 '#f3f1e9' $true
  Text ('THE WORKSPACE SERIES / '+$row.n) 1210 59 14 '#a8b9bb'
  Rect 64 213 26 3 $row.accent
  Text $row.label 104 200 17 $row.accent $true
  Text $row.title[0] 60 258 72 '#f3f1e9' $true
  Text $row.title[1] 60 337 72 $row.accent $true
  Text $row.copy[0] 65 458 21 '#bac7ca'
  Text $row.copy[1] 65 492 21 '#bac7ca'
  Text '00:00' 64 604 13 '#8aa0a2';Text '00:04' 186 604 13 '#8aa0a2';Text '00:08' 309 604 13 '#8aa0a2';Text '00:12' 432 604 13 '#8aa0a2'
  Rect 64 642 130 30 $row.accent;Rect 200 642 82 30 $row.accent;Rect 288 642 194 30 $row.accent
  Rect 64 681 255 14 '#40575b';Rect 325 681 157 14 '#40575b';Rect 280 633 1 78 '#eeeee4'
  $p=[Drawing.PointF[]]@([Drawing.PointF]::new(275,630),[Drawing.PointF]::new(286,630),[Drawing.PointF]::new(280.5,637));$b=Brush '#eeeee4';$graphics.FillPolygon($b,$p);$b.Dispose()
  Text 'INSIDE CUTROOM' 594 153 14 '#b8c7c7';Text $row.shot.ToUpperInvariant() 1430 153 14 $row.accent $true
  Rect 584 187 964 549 '#050a0d';Rect 590 188 952 539 '#668386'
  $src=if($row.shot -eq 'ai'){Join-Path $Repository 'docs\images\ai-options.png'}else{Join-Path $Repository ('docs\images\readme\studio-'+$row.shot+'-20261019.png')}
  $shot=[Drawing.Image]::FromFile($src)
  try{$graphics.DrawImage($shot,[Drawing.Rectangle]::new(594,192,944,531))}finally{$shot.Dispose()}
  Text 'ACTUAL INTERFACE / DEMO PROJECT / OCT 2026' 594 747 14 '#a7b7b8'
  Text $row.n 1474 750 42 $row.accent
  Rect 0 816 1600 84 '#111a1e'
  Rect 64 816 1472 1 '#435357'
  Text $row.detail 64 838 14 $row.accent
  Text 'cutroom-studio.expo.app' 1325 838 14 '#b4c2c3'
  $bitmap.Save((Join-Path $artOutput ($row.id+'-20261106.jpg')),$jpegEncoder,$jpegParams)
 } finally {$graphics.Dispose();$bitmap.Dispose()}
}
# A separate composition for social cards, with genuine screenshot pixels.
$bitmap=[Drawing.Bitmap]::new(1200,630);$graphics=[Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode='AntiAlias';$graphics.InterpolationMode='HighQualityBicubic';$graphics.TextRenderingHint='AntiAliasGridFit'
try{
 $graphics.DrawImage($artBackground,0,0,1200,630)
 $veil=[Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(85,10,17,20));$graphics.FillRectangle($veil,0,0,1200,630);$veil.Dispose()
 Logo 46 39 1.1;Text 'CUTROOM' 103 36 30 '#f3f1e9' $true
 Text 'FREE VIDEO EDITOR' 48 172 15 '#30d7c8' $true
 Text 'Every cut.' 44 214 61 '#f3f1e9' $true;Text 'Your call.' 44 282 61 '#30d7c8' $true
 Text 'Video. Sound. Captions.' 48 383 21 '#bac7ca'
 Text 'On your computer.' 48 416 21 '#bac7ca'
 Rect 421 139 736 420 '#668386'
 $shot=[Drawing.Image]::FromFile((Join-Path $Repository 'docs\images\editor.png'))
 try{$graphics.DrawImage($shot,[Drawing.Rectangle]::new(425,143,728,409))}finally{$shot.Dispose()}
 Text 'ACTUAL INTERFACE / DEMO PROJECT' 425 565 11 '#b4c2c3'
 Text 'OPEN SOURCE / 1.3 BETA' 49 565 13 '#30d7c8' $true
 Text 'cutroom-studio.expo.app' 906 51 15 '#b4c2c3'
 $bitmap.Save((Join-Path $artOutput 'social-20261106.jpg'),$jpegEncoder,$jpegParams)
}finally{$graphics.Dispose();$bitmap.Dispose();$artBackground.Dispose();$jpegParams.Dispose()}
Get-ChildItem -LiteralPath $artOutput -Filter '*.jpg' | Select-Object Name,Length
