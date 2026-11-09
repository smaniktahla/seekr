Imports System
Imports System.Collections.Generic
Imports System.Diagnostics
Imports System.IO
Imports System.Net
Imports System.Net.Sockets
Imports System.Text
Imports System.Threading.Tasks
Imports System.Web

' Loopback-only, ephemeral callback listener; no HTTP URL ACL or administrator needed.
Public Module GoogleDriveLogin
    Public Async Function Authorize(begin As Func(Of String,Task(Of Dictionary(Of String,Object))),Optional launch As Action(Of String)=Nothing) As Task(Of Dictionary(Of String,Object))
        Dim listener As New TcpListener(IPAddress.Loopback,0)
        listener.Start()
        Try
            Dim port=CType(listener.LocalEndpoint,IPEndPoint).Port
            Dim redirect="http://127.0.0.1:" & port & "/oauth2callback"
            Dim flow=Await begin(redirect)
            Dim url As New Uri(Convert.ToString(flow("authorization_url")))
            If url.Scheme<>"https" OrElse url.Host<>"accounts.google.com" OrElse url.UserInfo<>"" Then Throw New Exception("The service returned an invalid Google sign-in URL.")
            Dim expected=Convert.ToString(flow("state"))
            If launch Is Nothing Then
                Process.Start(New ProcessStartInfo(url.AbsoluteUri) With {.UseShellExecute=True})
            Else
                launch(url.AbsoluteUri)
            End If
            Dim deadline=Task.Delay(TimeSpan.FromMinutes(3))
            Do
                Dim accept=listener.AcceptTcpClientAsync()
                If Await Task.WhenAny(accept,deadline) Is deadline Then Throw New TimeoutException("Google sign-in timed out. Click Connect to try again.")
                Using socket=Await accept
                    Using stream=socket.GetStream()
                        Dim bytes As New List(Of Byte)()
                        Dim valid As Boolean=False
                        Dim code As String=Nothing
                        Dim denied As Boolean=False
                        ' Bound both request length and read time, including half-open connections.
                        Dim readDeadline=Task.Delay(TimeSpan.FromSeconds(5))
                        Do While bytes.Count<8192
                            Dim buffer(0) As Byte
                            Dim readTask=stream.ReadAsync(buffer,0,1)
                            If Await Task.WhenAny(readTask,readDeadline,deadline) IsNot readTask Then Exit Do
                            If Await readTask=0 Then Exit Do
                            bytes.Add(buffer(0))
                            If bytes.Count>=4 AndAlso Encoding.ASCII.GetString(bytes.ToArray()).EndsWith(vbCrLf & vbCrLf) Then
                                Dim first=Encoding.ASCII.GetString(bytes.ToArray()).Split(New String(){vbCrLf},StringSplitOptions.None)(0).Split(" "c)
                                Dim callback As Uri=Nothing
                                If first.Length=3 AndAlso first(0)="GET" AndAlso first(1).StartsWith("/oauth2callback?") AndAlso Uri.TryCreate("http://127.0.0.1:" & port & first(1),UriKind.Absolute,callback) Then
                                    Dim query=HttpUtility.ParseQueryString(callback.Query)
                                    valid=String.Equals(query("state"),expected,StringComparison.Ordinal)
                                    code=query("code") : denied=Not String.IsNullOrEmpty(query("error"))
                                    valid=valid AndAlso (denied OrElse Not String.IsNullOrEmpty(code))
                                End If
                                Exit Do
                            End If
                        Loop
                        Dim body=If(valid,"Seekr received the Google response. You can close this tab and return to Settings.","Invalid sign-in response. Return to Seekr.")
                        Dim reply=Encoding.UTF8.GetBytes("HTTP/1.1 " & If(valid,"200 OK","400 Bad Request") & vbCrLf & "Content-Type: text/plain; charset=utf-8" & vbCrLf & "Cache-Control: no-store" & vbCrLf & "Connection: close" & vbCrLf & "Content-Length: " & Encoding.UTF8.GetByteCount(body) & vbCrLf & vbCrLf & body)
                        Dim writeTask=stream.WriteAsync(reply,0,reply.Length)
                        Await Task.WhenAny(writeTask,Task.Delay(1000))
                        If valid Then
                            If denied Then Throw New Exception("Google sign-in was declined. No connection was saved.")
                            Return New Dictionary(Of String,Object) From {{"state",expected},{"code",code}}
                        End If
                    End Using
                End Using
            Loop
        Finally
            listener.Stop()
        End Try
    End Function
End Module
