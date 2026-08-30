param(
    [string]$PatternsPath = "$PSScriptRoot\..\work\ppsspp_memory_requests.json",
    [string]$Uri = 'ws://127.0.0.1:4543/debugger',
    [uint32]$StartAddress = 0x08000000,
    [uint32]$TotalSize = 0x04000000,
    [uint32]$ChunkSize = 0x00400000
)

$ErrorActionPreference = 'Stop'
$requestObjects = Get-Content -LiteralPath $PatternsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$patterns = @(
    foreach ($item in $requestObjects) {
        if ($item.base64) {
            $patternBytes = [Convert]::FromBase64String([string]$item.base64)
            [PSCustomObject]@{
                Label = [string]$item.ticket
                Bytes = $patternBytes
                Hex = [BitConverter]::ToString($patternBytes).Replace('-', '')
            }
        }
    }
)
if ($patterns.Count -eq 0) { throw 'No base64 patterns found.' }
$overlap = ($patterns | ForEach-Object { $_.Bytes.Length } | Measure-Object -Maximum).Maximum - 1

$socket = [System.Net.WebSockets.ClientWebSocket]::new()
$socket.Options.AddSubProtocol('debugger.ppsspp.org')
$cancel = [Threading.CancellationToken]::None
$null = $socket.ConnectAsync([Uri]$Uri, $cancel).GetAwaiter().GetResult()
$found = @{}
foreach ($pattern in $patterns) { $found[$pattern.Label] = [Collections.Generic.List[uint32]]::new() }

function Receive-Ticket([string]$ticket) {
    while ($true) {
        $stream = [IO.MemoryStream]::new()
        try {
            do {
                $buffer = [byte[]]::new(262144)
                $part = [ArraySegment[byte]]::new($buffer)
                $result = $socket.ReceiveAsync($part, $cancel).GetAwaiter().GetResult()
                if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                    throw 'PPSSPP debugger closed the WebSocket.'
                }
                $stream.Write($buffer, 0, $result.Count)
            } while (-not $result.EndOfMessage)
            $response = [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
            if ($response.ticket -eq $ticket) { return $response }
        } finally {
            $stream.Dispose()
        }
    }
}

try {
    for ([uint64]$offset = 0; $offset -lt $TotalSize; $offset += $ChunkSize) {
        $readSize = [Math]::Min([uint64]$ChunkSize + $overlap, [uint64]$TotalSize - $offset)
        $ticket = 'chunk-{0:X8}' -f $offset
        $request = @{
            event = 'memory.read'
            ticket = $ticket
            address = [uint64]$StartAddress + $offset
            size = $readSize
        } | ConvertTo-Json -Compress
        $rawRequest = [Text.Encoding]::UTF8.GetBytes($request)
        $segment = [ArraySegment[byte]]::new($rawRequest)
        $null = $socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cancel).GetAwaiter().GetResult()
        $response = Receive-Ticket $ticket
        if ($response.event -eq 'error') {
            $errorAddress = '0x{0:X8}' -f [uint32]([uint64]$StartAddress + $offset)
            $errorSize = '0x{0:X}' -f [uint32]$readSize
            throw ("$($response.message) at address $errorAddress, size $errorSize")
        }
        $data = [Convert]::FromBase64String([string]$response.base64)
        $hex = [BitConverter]::ToString($data).Replace('-', '')
        foreach ($pattern in $patterns) {
            $from = 0
            while ($true) {
                $at = $hex.IndexOf($pattern.Hex, $from, [StringComparison]::Ordinal)
                if ($at -lt 0) { break }
                $byteOffset = [uint32]($at / 2)
                if ($byteOffset -lt $ChunkSize) {
                    $found[$pattern.Label].Add([uint32]([uint64]$StartAddress + $offset + $byteOffset))
                }
                $from = $at + 2
            }
        }
        Write-Progress -Activity 'PPSSPP RAM scan' -Status ('0x{0:X8}' -f ([uint64]$StartAddress + $offset)) -PercentComplete (100 * ($offset + $readSize) / $TotalSize)
    }
    Write-Progress -Activity 'PPSSPP RAM scan' -Completed
    foreach ($pattern in $patterns) {
        $addresses = @($found[$pattern.Label] | ForEach-Object { '0x{0:X8}' -f $_ })
        [PSCustomObject]@{
            pattern = $pattern.Label
            count = $addresses.Count
            addresses = $addresses
        } | ConvertTo-Json -Compress
    }
} finally {
    if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $null = $socket.CloseOutputAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', $cancel).GetAwaiter().GetResult()
    }
    $socket.Dispose()
}
