<#
  Arranges the Explorer window that the app's "Open folder" button opened:
  moves it to a fixed spot on the primary screen, switches to large icons,
  selects the file, and optionally toggles the Details pane (Alt+Shift+P).
  Prints the window rectangle as "x y w h".
#>
param(
  [Parameter(Mandatory)][string]$Folder,
  [Parameter(Mandatory)][string]$File,
  [int]$X = 160, [int]$Y = 120, [int]$W = 1600, [int]$H = 860,
  [switch]$ToggleDetails,
  [int]$TimeoutSec = 15
)
$ErrorActionPreference = 'Stop'
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class W32 {
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
'@
$shell = New-Object -ComObject Shell.Application
$want = ([Uri](Resolve-Path $Folder).Path).AbsoluteUri.TrimEnd('/')
$win = $null
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while (-not $win -and (Get-Date) -lt $deadline) {
  $win = @($shell.Windows()) | Where-Object { $_.LocationURL -and $_.LocationURL.TrimEnd('/') -ieq $want } | Select-Object -First 1
  if (-not $win) { Start-Sleep -Milliseconds 300 }
}
if (-not $win) { throw "Explorer window for $Folder not found" }
$h = [IntPtr]$win.HWND
[W32]::ShowWindow($h, 9) | Out-Null          # restore if maximized
[W32]::MoveWindow($h, $X, $Y, $W, $H, $true) | Out-Null
[W32]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 400
$doc = $win.Document
$doc.CurrentViewMode = 1                     # icons
$doc.IconSize = 256                          # extra large, shows the cover art
$item = $doc.Folder.ParseName($File)
if (-not $item) { throw "File $File not in $Folder" }
$doc.SelectItem($item, 1 + 4 + 8 + 16)       # select, deselect others, ensure visible, focus
if ($ToggleDetails) {
  Add-Type -AssemblyName System.Windows.Forms
  [W32]::SetForegroundWindow($h) | Out-Null
  Start-Sleep -Milliseconds 300
  [System.Windows.Forms.SendKeys]::SendWait('%+p')
}
"$X $Y $W $H"
