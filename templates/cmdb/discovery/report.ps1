# PackDesk discovery for Windows: reports this computer and, with -Neighbours, the devices it already knows on the
# network (from its own address table; it does not scan). Run it by hand or from Task Scheduler, e.g. once a day:
#   powershell -ExecutionPolicy Bypass -File packdesk-discovery.ps1 -Key <key> [-Neighbours]
param(
  [Parameter(Mandatory = $true)][string]$Key,
  [switch]$Neighbours
)
$ErrorActionPreference = "Stop"
$Url = "{{ report_url }}"

$system = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
$os = Get-CimInstance Win32_OperatingSystem
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
  Select-Object -First 1 -ExpandProperty IPAddress

$serial = "$($bios.SerialNumber)".Trim()
$identity = if ($serial) { $serial } else { $env:COMPUTERNAME }
$items = @(@{
  key = $identity; name = $env:COMPUTERNAME; manufacturer = $system.Manufacturer; model = $system.Model; serial_nr = $serial
  properties = @{ ip_address = $ip; operating_system = $os.Caption }
})

if ($Neighbours) {
  Get-NetNeighbor -AddressFamily IPv4 -State Reachable, Stale -ErrorAction SilentlyContinue |
    Where-Object { $_.LinkLayerAddress -and $_.LinkLayerAddress -ne "00-00-00-00-00-00" } |
    ForEach-Object {
      $items += @{ key = $_.LinkLayerAddress; name = $_.IPAddress
                   properties = @{ ip_address = $_.IPAddress; mac_address = $_.LinkLayerAddress } }
    }
}

$body = @{ items = $items } | ConvertTo-Json -Depth 4
$result = Invoke-RestMethod -Method Post -Uri $Url -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
  -ContentType "application/json" -Headers @{ Authorization = "Bearer $Key" }
$result | ConvertTo-Json -Compress
