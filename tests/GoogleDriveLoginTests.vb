Imports System
Imports System.Collections.Generic
Imports System.Net.Http
Imports System.Threading.Tasks

Module GoogleDriveLoginTests
    Sub Main()
        Run().GetAwaiter().GetResult()
        Console.WriteLine("Windows OAuth callback checks passed.")
    End Sub
    Private Async Function Run() As Task
        Dim redirect As String=Nothing
        Dim browser As Task=Nothing
        Dim begin As Func(Of String,Task(Of Dictionary(Of String,Object))) = Function(callback)
            redirect=callback
            Return Task.FromResult(New Dictionary(Of String,Object) From {{"authorization_url","https://accounts.google.com/o/oauth2/auth"},{"state","synthetic-state"}})
        End Function
        Dim launch As Action(Of String) = Sub(url)
            browser=Task.Run(Async Function()
                Using client As New HttpClient(New HttpClientHandler With {.UseProxy=False})
                    client.Timeout=TimeSpan.FromSeconds(10)
                    Dim invalid=Await client.GetAsync(redirect & "?state=wrong&code=bad")
                    If CInt(invalid.StatusCode)<>400 Then Throw New Exception("Invalid state accepted")
                    Dim valid=Await client.GetAsync(redirect & "?state=synthetic-state&code=synthetic%2Bcode")
                    If CInt(valid.StatusCode)<>200 Then Throw New Exception("Valid callback rejected")
                End Using
            End Function)
        End Sub
        Dim result=Await GoogleDriveLogin.Authorize(begin,launch)
        Await browser
        If CStr(result("code"))<>"synthetic+code" Then Throw New Exception("Authorization code decoding failed")
        Dim opened As Boolean=False
        Try
            Await GoogleDriveLogin.Authorize(Function(callback) Task.FromResult(New Dictionary(Of String,Object) From {{"authorization_url","https://example.test/login"},{"state","state"}}),Sub(url) opened=True)
            Throw New Exception("Non-Google URL accepted")
        Catch ex As Exception When ex.Message="The service returned an invalid Google sign-in URL."
        End Try
        If opened Then Throw New Exception("Non-Google URL opened")
    End Function
End Module
