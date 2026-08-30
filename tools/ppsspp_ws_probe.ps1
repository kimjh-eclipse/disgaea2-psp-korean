param(
    [Parameter(Mandatory = $true)]
    [string]$RequestsPath,
    [string]$Uri = 'ws://127.0.0.1:4543/debugger'
)

$ErrorActionPreference = 'Stop'
$socket = [System.Net.WebSockets.ClientWebSocket]::new()
$socket.Options.AddSubProtocol('debugger.ppsspp.org')
$cancel = [Threading.CancellationToken]::None
$null = $socket.ConnectAsync([Uri]$Uri, $cancel).GetAwaiter().GetResult()

try {
    $requests = Get-Content -LiteralPath $RequestsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($request in $requests) {
        $json = $request | ConvertTo-Json -Compress -Depth 8
        $bytes = [Text.Encoding]::UTF8.GetBytes($json)
        $segment = [ArraySegment[byte]]::new($bytes)
        $null = $socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cancel).GetAwaiter().GetResult()

        while ($true) {
            $stream = [IO.MemoryStream]::new()
            try {
                do {
                    $buffer = [byte[]]::new(65536)
                    $part = [ArraySegment[byte]]::new($buffer)
                    $result = $socket.ReceiveAsync($part, $cancel).GetAwaiter().GetResult()
                    if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                        throw 'PPSSPP debugger closed the WebSocket.'
                    }
                    $stream.Write($buffer, 0, $result.Count)
                } while (-not $result.EndOfMessage)
                $responseText = [Text.Encoding]::UTF8.GetString($stream.ToArray())
                $response = $responseText | ConvertFrom-Json
                if ($response.ticket -eq $request.ticket) {
                    $responseText
                    break
                }
            } finally {
                $stream.Dispose()
            }
        }
    }
} finally {
    if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $null = $socket.CloseOutputAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', $cancel).GetAwaiter().GetResult()
    }
    $socket.Dispose()
}
