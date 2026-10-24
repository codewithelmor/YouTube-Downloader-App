<#
  Moves the real mouse cursor smoothly through screen points, for the Explorer scene.
  -Path "x1,y1,pauseMs;x2,y2,pauseMs;..."  (the first point is a jump)
#>
param([Parameter(Mandatory)][string]$Path, [int]$StepMs = 15, [int]$MoveMs = 700)
Add-Type -AssemblyName System.Windows.Forms
$pts = $Path.Split(';') | ForEach-Object { $a = $_.Split(','); @{ x = [int]$a[0]; y = [int]$a[1]; p = [int]$a[2] } }
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($pts[0].x, $pts[0].y)
Start-Sleep -Milliseconds $pts[0].p
for ($i = 1; $i -lt $pts.Count; $i++) {
  $from = [System.Windows.Forms.Cursor]::Position; $to = $pts[$i]
  $n = [math]::Max(1, [int]($MoveMs / $StepMs))
  for ($k = 1; $k -le $n; $k++) {
    $t = $k / $n; $e = $t * $t * (3 - 2 * $t)          # ease in-out
    $x = [int]($from.X + ($to.x - $from.X) * $e); $y = [int]($from.Y + ($to.y - $from.Y) * $e)
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($x, $y)
    Start-Sleep -Milliseconds $StepMs
  }
  Start-Sleep -Milliseconds $to.p
}
