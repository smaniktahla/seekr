Imports System
Imports System.IO
Imports System.Net.Http
Imports System.Net.Http.Headers
Imports System.Web.Script.Serialization
Imports System.Collections.Generic
Imports System.Windows.Forms
Imports System.Drawing
Imports System.Security.Cryptography
Imports System.Text
Imports System.Diagnostics
Imports System.Threading.Tasks

Public Class SearchWindow
    Inherits Form
    Private ReadOnly query As New TextBox()
    Private ReadOnly clearQueryButton As New Button()
    Private ReadOnly searchToolTip As New ToolTip()
    Private ReadOnly category As New ComboBox()
    Private ReadOnly share As New ComboBox()
    Private ReadOnly mode As New ComboBox()
    Private ReadOnly clearFiltersButton As New Button()
    Private ReadOnly autoClearFilters As New CheckBox()
    Private ReadOnly searchButton As New Button()
    Private ReadOnly settingsButton As New Button With {.Text="Settings...",.AutoSize=True}
    Private ReadOnly openButton As New Button()
    Private ReadOnly folderButton As New Button()
    Private ReadOnly copyButton As New Button()
    Private ReadOnly nextButton As New Button()
    Private ReadOnly readMore As New Button()
    Private ReadOnly grid As New DataGridView()
    Private ReadOnly preview As New TextBox()
    Private ReadOnly info As New Label()
    Private ReadOnly http As New HttpClient(New HttpClientHandler With {.UseProxy=False})
    Private ReadOnly serializer As New JavaScriptSerializer()
    Private rows As New List(Of Dictionary(Of String,Object))()
    Private offset As Integer = 0
    Private previewOffset As Integer = 0
    Private nextPreview As Integer = -1
    Private activeId As Integer = -1
    Private generation As Integer = 0
    Private activeSearchUrl As String = Nothing
    Private activeSearchType As String = "all"
    Private ReadOnly liveTimer As New System.Windows.Forms.Timer With {.Interval=250}
    Private searchCancellation As Threading.CancellationTokenSource
    Private searchGeneration As Integer = 0
    Private searchReady As Boolean = False
    Private resettingFilters As Boolean = False
    Private activeLiveSearch As Boolean = False
    Private preferredShare As String = Nothing
    Private endpoint As String = ResolveEndpoint()
    Private Shared Function ResolveEndpoint() As String
        Dim configured=Environment.GetEnvironmentVariable("ARCHIVE_SEARCH_URL")
        If Not String.IsNullOrWhiteSpace(configured) Then Return configured.TrimEnd("/"c)
        Dim savedPath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NASArchiveSearch","service.json")
        If File.Exists(savedPath) Then
            Dim saved=New JavaScriptSerializer().Deserialize(Of Dictionary(Of String,String))(File.ReadAllText(savedPath))
            If saved.ContainsKey("url") Then Return saved("url").TrimEnd("/"c)
        End If
        Dim configPath=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"client.json")
        If File.Exists(configPath) Then
            Dim config=New JavaScriptSerializer().Deserialize(Of Dictionary(Of String,String))(File.ReadAllText(configPath))
            If config.ContainsKey("url") Then Return config("url").TrimEnd("/"c)
        End If
        Return "http://localhost:8093"
    End Function

    Public Sub New()
        Text="NAS Archive Search" : Size=New Size(1150,800) : MinimumSize=New Size(800,580)
        Me.Icon=Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath)
        StartPosition=FormStartPosition.CenterScreen : Font=New Font("Segoe UI",10)
        BackColor=Color.FromArgb(245,243,238)
        Dim layout As New TableLayoutPanel With {.Dock=DockStyle.Fill,.ColumnCount=1,.RowCount=5,.Padding=New Padding(18)}
        layout.RowStyles.Add(New RowStyle(SizeType.Absolute,45))
        layout.RowStyles.Add(New RowStyle(SizeType.Absolute,44))
        layout.RowStyles.Add(New RowStyle(SizeType.Absolute,78))
        layout.RowStyles.Add(New RowStyle(SizeType.Percent,100))
        layout.RowStyles.Add(New RowStyle(SizeType.Absolute,46))
        Dim heading As New Label With {.Text="Archive Search",.Font=New Font("Segoe UI",22,FontStyle.Bold),.AutoSize=True}
        Dim headingBar As New TableLayoutPanel With {.Dock=DockStyle.Fill,.ColumnCount=2,.RowCount=1}
        headingBar.ColumnStyles.Add(New ColumnStyle(SizeType.Percent,100)) : headingBar.ColumnStyles.Add(New ColumnStyle(SizeType.Absolute,120))
        headingBar.Controls.Add(heading,0,0) : headingBar.Controls.Add(settingsButton,1,0) : layout.Controls.Add(headingBar,0,0)
        AddHandler settingsButton.Click, Sub(s,e)
            Try
                OpenSettings()
            Catch ex As Exception
                MessageBox.Show(ex.Message,"Seekr settings")
            End Try
        End Sub
        Dim bar As New TableLayoutPanel With {.Dock=DockStyle.Fill,.ColumnCount=2}
        bar.ColumnStyles.Add(New ColumnStyle(SizeType.Percent,100)) : bar.ColumnStyles.Add(New ColumnStyle(SizeType.Absolute,110))
        Dim queryBar As New TableLayoutPanel With {.Dock=DockStyle.Fill,.ColumnCount=2,.RowCount=1,.BackColor=Color.White,.BorderStyle=BorderStyle.FixedSingle,.Padding=New Padding(5,3,2,3)}
        queryBar.ColumnStyles.Add(New ColumnStyle(SizeType.Percent,100))
        queryBar.ColumnStyles.Add(New ColumnStyle(SizeType.Absolute,30))
        query.Dock=DockStyle.Fill : query.BorderStyle=BorderStyle.None
        clearQueryButton.Text=ChrW(&HD7) : clearQueryButton.Dock=DockStyle.Fill
        clearQueryButton.FlatStyle=FlatStyle.Flat : clearQueryButton.FlatAppearance.BorderSize=0
        clearQueryButton.Margin=New Padding(0) : clearQueryButton.Font=New Font("Segoe UI",12)
        clearQueryButton.AccessibleName="Clear search" : clearQueryButton.Enabled=False
        searchToolTip.SetToolTip(clearQueryButton,"Clear search")
        queryBar.Controls.Add(query,0,0) : queryBar.Controls.Add(clearQueryButton,1,0)
        searchButton.Text="Search" : searchButton.Dock=DockStyle.Fill
        bar.Controls.Add(queryBar,0,0) : bar.Controls.Add(searchButton,1,0) : layout.Controls.Add(bar,0,1)
        AddHandler clearQueryButton.Click, Sub(s,e)
            query.Clear() : query.Focus()
        End Sub
        Dim filters As New FlowLayoutPanel With {.Dock=DockStyle.Fill}
        category.DropDownStyle=ComboBoxStyle.DropDownList : category.Items.AddRange(New Object(){"all","documents","pictures","music","videos","other"}) : category.SelectedIndex=0
        share.DropDownStyle=ComboBoxStyle.DropDownList : share.Items.AddRange(New Object(){"all","Documents","Pictures","Music","Videos"}) : share.SelectedIndex=0
        mode.DropDownStyle=ComboBoxStyle.DropDownList : mode.Items.AddRange(New Object(){"keyword","hybrid","semantic"}) : mode.SelectedIndex=0
        autoClearFilters.Text="Clear filters after each search" : autoClearFilters.AutoSize=True : autoClearFilters.Checked=True
        autoClearFilters.Margin=New Padding(12,7,0,0)
        LoadFilters()
        AddHandler category.SelectedIndexChanged, Sub(s,e) FiltersChanged()
        AddHandler share.SelectedIndexChanged, Sub(s,e) FiltersChanged()
        AddHandler mode.SelectedIndexChanged, Sub(s,e) FiltersChanged()
        AddHandler autoClearFilters.CheckedChanged, Sub(s,e) SaveFilters()
        filters.Controls.Add(New Label With {.Text="Type",.AutoSize=True,.Padding=New Padding(0,5,0,0)}) : filters.Controls.Add(category)
        filters.Controls.Add(New Label With {.Text="Share",.AutoSize=True,.Padding=New Padding(8,5,0,0)}) : filters.Controls.Add(share)
        filters.Controls.Add(New Label With {.Text="Search",.AutoSize=True,.Padding=New Padding(8,5,0,0)}) : filters.Controls.Add(mode)
        nextButton.Text="Next page" : filters.Controls.Add(nextButton) : nextButton.Enabled=False
        filters.SetFlowBreak(nextButton,True)
        clearFiltersButton.Text="Clear filters" : clearFiltersButton.AutoSize=True
        filters.Controls.Add(clearFiltersButton) : filters.Controls.Add(autoClearFilters)
        AddHandler clearFiltersButton.Click, Sub(s,e)
            ClearFilters() : ScheduleLiveSearch()
        End Sub
        filters.Controls.Add(New Label With {.Text="Typing: filenames / paths. Enter: full text.",.AutoSize=True,.Padding=New Padding(12,7,0,0)})
        layout.Controls.Add(filters,0,2)
        Dim split As New SplitContainer With {.Dock=DockStyle.Fill,.Orientation=Orientation.Horizontal,.SplitterDistance=260}
        grid.Dock=DockStyle.Fill : grid.ReadOnly=True : grid.AllowUserToAddRows=False : grid.AllowUserToDeleteRows=False
        grid.MultiSelect=False : grid.SelectionMode=DataGridViewSelectionMode.FullRowSelect : grid.AutoGenerateColumns=False
        grid.RowHeadersVisible=False : grid.BackgroundColor=Color.White : grid.AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill
        grid.Columns.Add("Name","Name") : grid.Columns(0).FillWeight=32
        grid.Columns.Add("Type","Type") : grid.Columns(1).FillWeight=8
        grid.Columns.Add("Share","Share") : grid.Columns(2).FillWeight=12
        grid.Columns.Add("State","Indexed content") : grid.Columns(3).FillWeight=14
        grid.Columns.Add("Path","Original path") : grid.Columns(4).FillWeight=34
        Dim itemMenu As New ContextMenuStrip()
        Dim menuOpen As New ToolStripMenuItem("Open")
        Dim menuFolder As New ToolStripMenuItem("Open folder in Explorer")
        itemMenu.Items.AddRange(New ToolStripItem(){menuOpen,menuFolder})
        grid.ContextMenuStrip=itemMenu
        AddHandler menuOpen.Click, Sub(s,e) OpenOriginal()
        AddHandler menuFolder.Click, Sub(s,e) ShowInExplorer()
        AddHandler grid.CellMouseDown, Sub(s,e)
            If e.Button<>MouseButtons.Right Then Return
            grid.ClearSelection()
            If e.RowIndex<0 Then
                grid.CurrentCell=Nothing
                Return
            End If
            grid.CurrentCell=grid.Rows(e.RowIndex).Cells(Math.Max(0,e.ColumnIndex))
            grid.Rows(e.RowIndex).Selected=True
        End Sub
        AddHandler itemMenu.Opening, Sub(s,e)
            e.Cancel=(Selected() Is Nothing)
            menuFolder.Enabled=(SelectedPath()<>"")
        End Sub
        split.Panel1.Controls.Add(grid)
        preview.Multiline=True : preview.ReadOnly=True : preview.ScrollBars=ScrollBars.Both : preview.Dock=DockStyle.Fill : preview.Font=New Font("Consolas",10)
        split.Panel2.Controls.Add(preview) : layout.Controls.Add(split,0,3)
        Dim footer As New FlowLayoutPanel With {.Dock=DockStyle.Fill}
        openButton.Text="Open Original" : openButton.AutoSize=True : folderButton.Text="Show in Explorer" : folderButton.AutoSize=True
        copyButton.Text="Copy path" : copyButton.AutoSize=True : readMore.Text="Next text section" : readMore.AutoSize=True : readMore.Enabled=False
        info.AutoSize=True : info.Padding=New Padding(8,7,0,0) : info.Text="NAS copy updates after backup and indexing."
        footer.Controls.AddRange(New Control(){openButton,folderButton,copyButton,readMore,info}) : layout.Controls.Add(footer,0,4)
        Controls.Add(layout) : AcceptButton=searchButton
        http.Timeout=TimeSpan.FromSeconds(30)
        serializer.MaxJsonLength=4*1024*1024
        AddHandler searchButton.Click, Async Sub(s,e)
            offset=0 : Await RunSearch()
        End Sub
        AddHandler nextButton.Click, Async Sub(s,e)
            offset+=20 : Await RunSearch(False,activeLiveSearch)
        End Sub
        AddHandler query.TextChanged, Sub(s,e)
            clearQueryButton.Enabled=(query.TextLength>0)
            ScheduleLiveSearch()
        End Sub
        AddHandler liveTimer.Tick, Async Sub(s,e)
            liveTimer.Stop() : offset=0 : Await RunSearch(True,True)
        End Sub
        AddHandler FormClosed, Sub(s,e)
            liveTimer.Dispose()
            If searchCancellation IsNot Nothing Then searchCancellation.Cancel()
            http.Dispose()
        End Sub
        AddHandler grid.SelectionChanged, Async Sub(s,e)
            Await LoadPreview(0)
        End Sub
        AddHandler grid.CellDoubleClick, Sub(s,e) OpenOriginal()
        AddHandler openButton.Click, Sub(s,e) OpenOriginal()
        AddHandler folderButton.Click, Sub(s,e) ShowInExplorer()
        AddHandler copyButton.Click, Sub(s,e)
            Dim p=SelectedPath()
            If p<>"" Then Clipboard.SetText(p)
        End Sub
        AddHandler readMore.Click, Async Sub(s,e)
            If nextPreview>=0 Then Await LoadPreview(nextPreview)
        End Sub
        AddHandler Shown, Async Sub(s,e)
            Try
                Dim keyPath=ServiceTokenPath(endpoint)
                If Not File.Exists(keyPath) Then keyPath=Path.Combine(Application.StartupPath,"archive-token.dpapi")
                Dim token=Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(keyPath),Nothing,DataProtectionScope.CurrentUser)).Trim()
                http.DefaultRequestHeaders.Authorization=New AuthenticationHeaderValue("Bearer",token)
                searchReady=True
                Dim data=Await GetJson("/api/status")
                info.Text=Convert.ToInt32(data("files")).ToString("N0") & " files available"
                Try
                    ApplySourceSettings(Await GetJson("/api/settings"))
                Catch
                    ' Older services still support ordinary archive searches.
                End Try
            Catch ex As Exception
                If Environment.GetCommandLineArgs().Contains("--smoke") Then
                    File.WriteAllText(Path.Combine(Application.StartupPath,"smoke-result.txt"),"STARTUP ERROR: " & ex.ToString())
                    Close() : Return
                End If
                MessageBox.Show("Cannot connect or load your Windows-protected credential: " & ex.Message,"Archive Search")
            End Try
            If Environment.GetCommandLineArgs().Contains("--smoke") OrElse Environment.GetCommandLineArgs().Contains("--smoke-live") Then
                Try
                    If Environment.GetCommandLineArgs().Contains("--smoke-live") Then
                        Dim originalFilters=category.Text & "/" & share.Text & "/" & mode.Text
                        query.Text="int"
                        Dim olderSearch=RunSearch(True,True)
                        query.Text="bmw intake" : Await RunSearch(True,True)
                        Await olderSearch
                        If rows.Count=0 OrElse Not activeSearchUrl.Contains("mode=filename") Then Throw New Exception("Live filename search failed")
                        For Each row In rows
                            Dim resultPath=Convert.ToString(row("unc_path")).ToLowerInvariant()
                            If Not resultPath.Contains("bmw") OrElse Not resultPath.Contains("intake") Then Throw New Exception("Stale response replaced current results")
                        Next
                        If originalFilters<>category.Text & "/" & share.Text & "/" & mode.Text Then Throw New Exception("Live update cleared filters")
                    Else
                        query.Text="tuition" : Await RunSearch()
                    End If
                    File.WriteAllText(Path.Combine(Application.StartupPath,"smoke-result.txt"),"Rows: " & grid.Rows.Count & Environment.NewLine & info.Text & Environment.NewLine & preview.Text)
                Catch ex As Exception
                    File.WriteAllText(Path.Combine(Application.StartupPath,"smoke-result.txt"),"SEARCH ERROR: " & ex.ToString())
                Finally
                    Close()
                End Try
            End If
        End Sub
    End Sub

    Private Sub ApplySourceSettings(config As Dictionary(Of String,Object))
        resettingFilters=True
        Try
            Dim selectedShare=If(preferredShare,share.Text)
            preferredShare=Nothing
            share.Items.Clear() : share.Items.Add("all")
            For Each item As Object In CType(config("sources"),System.Collections.IEnumerable)
                Dim source=CType(item,Dictionary(Of String,Object))
                If Convert.ToBoolean(source("enabled")) Then share.Items.Add(Convert.ToString(source("id")))
            Next
            If Convert.ToBoolean(CType(config("docmost"),Dictionary(Of String,Object))("enabled")) Then share.Items.Add("DocMost")
            share.SelectedItem=If(share.Items.Contains(selectedShare),selectedShare,"all")
        Finally
            resettingFilters=False
        End Try
    End Sub
    Private Sub OpenSettings()
        liveTimer.Stop() : searchGeneration+=1
        If searchCancellation IsNot Nothing Then searchCancellation.Cancel()
        searchButton.Enabled=True
        Dim token=If(http.DefaultRequestHeaders.Authorization Is Nothing,"",http.DefaultRequestHeaders.Authorization.Parameter)
        Dim statePath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NASArchiveSearch","service.json")
        Dim nasUrl=endpoint
        Try
            If File.Exists(statePath) Then
                Dim saved=serializer.Deserialize(Of Dictionary(Of String,String))(File.ReadAllText(statePath))
                If saved.ContainsKey("nas_url") Then nasUrl=saved("nas_url")
            End If
        Catch
        End Try
        Using dialog As New SettingsWindow(endpoint,token,nasUrl)
            If dialog.ShowDialog(Me)<>DialogResult.OK Then Return
            endpoint=dialog.ServiceUrl
            http.DefaultRequestHeaders.Authorization=New AuthenticationHeaderValue("Bearer",dialog.Token)
            Directory.CreateDirectory(Path.GetDirectoryName(statePath))
            Dim saved As New Dictionary(Of String,String) From {{"url",endpoint},{"nas_url",If(New Uri(endpoint).IsLoopback,nasUrl,endpoint)}}
            File.WriteAllText(statePath,serializer.Serialize(saved))
            Dim keyPath=ServiceTokenPath(endpoint)
            File.WriteAllBytes(keyPath,ProtectedData.Protect(Encoding.UTF8.GetBytes(dialog.Token),Nothing,DataProtectionScope.CurrentUser))
            ApplySourceSettings(dialog.Configuration)
            generation+=1 : rows.Clear() : grid.Rows.Clear() : preview.Clear()
            activeSearchUrl=Nothing : nextButton.Enabled=False : readMore.Enabled=False
            info.Text="Settings saved. Background indexing will rescan."
            ScheduleLiveSearch()
        End Using
    End Sub
    Private Shared Function ServiceTokenPath(url As String) As String
        Dim folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NASArchiveSearch")
        Directory.CreateDirectory(folder)
        Using hash=SHA256.Create()
            Dim name=BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(url))).Replace("-","").Substring(0,24)
            Return Path.Combine(folder,"token-" & name & ".dpapi")
        End Using
    End Function

    Private Function FilterSettingsPath() As String
        Return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NASArchiveSearch","filters.json")
    End Function
    Private Sub LoadFilters()
        Try
            Dim settingsPath=FilterSettingsPath()
            If Not File.Exists(settingsPath) Then Return
            Dim saved=serializer.Deserialize(Of Dictionary(Of String,String))(File.ReadAllText(settingsPath))
            For Each entry In New KeyValuePair(Of String,ComboBox)(){New KeyValuePair(Of String,ComboBox)("category",category),New KeyValuePair(Of String,ComboBox)("share",share),New KeyValuePair(Of String,ComboBox)("mode",mode)}
                If saved.ContainsKey(entry.Key) AndAlso entry.Value.Items.Contains(saved(entry.Key)) Then entry.Value.SelectedItem=saved(entry.Key)
            Next
            If saved.ContainsKey("autoClear") Then
                Dim enabled As Boolean
                If Boolean.TryParse(saved("autoClear"),enabled) Then autoClearFilters.Checked=enabled
            End If
            If autoClearFilters.Checked Then
                category.SelectedIndex=0 : share.SelectedIndex=0 : mode.SelectedIndex=0
            ElseIf saved.ContainsKey("share") Then
                preferredShare=saved("share")
            End If
        Catch
            ' Missing or invalid preferences leave the first-launch defaults intact.
        End Try
    End Sub
    Private Sub SaveFilters()
        Try
            Dim settingsPath=FilterSettingsPath()
            Directory.CreateDirectory(Path.GetDirectoryName(settingsPath))
            Dim saved As New Dictionary(Of String,String) From {{"category",category.Text},{"share",share.Text},{"mode",mode.Text},{"autoClear",autoClearFilters.Checked.ToString()}}
            File.WriteAllText(settingsPath,serializer.Serialize(saved))
        Catch
            ' Search remains usable if preferences cannot be saved.
        End Try
    End Sub
    Private Sub ClearFilters()
        resettingFilters=True
        Try
            category.SelectedIndex=0 : share.SelectedIndex=0 : mode.SelectedIndex=0
            SaveFilters()
        Finally
            resettingFilters=False
        End Try
    End Sub
    Private Sub FiltersChanged()
        SaveFilters()
        If Not resettingFilters Then ScheduleLiveSearch()
    End Sub
    Private Sub ScheduleLiveSearch()
        liveTimer.Stop() : searchGeneration+=1
        If searchCancellation IsNot Nothing Then searchCancellation.Cancel()
        searchButton.Enabled=True
        nextButton.Enabled=False
        If Not searchReady Then Return
        If query.Text.Trim().Length>=2 Then
            liveTimer.Start()
        Else
            generation+=1 : rows.Clear() : grid.Rows.Clear() : preview.Clear()
            nextButton.Enabled=False : readMore.Enabled=False : activeSearchUrl=Nothing
            info.Text="Type at least 2 characters; Enter searches full text."
        End If
    End Sub
    Private Async Function GetJson(url As String,Optional cancellation As Threading.CancellationToken=Nothing) As Task(Of Dictionary(Of String,Object))
        Dim r=Await http.GetAsync(endpoint & url,cancellation)
        r.EnsureSuccessStatusCode()
        Return serializer.Deserialize(Of Dictionary(Of String,Object))(Await r.Content.ReadAsStringAsync())
    End Function
    Private Async Function RunSearch(Optional useCurrentFilters As Boolean=True,Optional live As Boolean=False) As Task
        If String.IsNullOrWhiteSpace(query.Text) Then Return
        liveTimer.Stop() : searchGeneration+=1 : Dim requestNumber=searchGeneration
        If searchCancellation IsNot Nothing Then
            searchCancellation.Cancel() : searchCancellation.Dispose()
        End If
        searchCancellation=New Threading.CancellationTokenSource()
        Dim requestCancellation=searchCancellation.Token
        searchButton.Enabled=live : info.Text=If(live,"Matching filenames...","Searching contents...")
        Try
            If useCurrentFilters OrElse activeSearchUrl Is Nothing Then
                activeSearchUrl="/api/search?q=" & Uri.EscapeDataString(query.Text) & "&category=" & category.Text & "&share=" & share.Text & "&mode=" & If(live,"filename",mode.Text) & "&limit=20"
                activeSearchType=category.Text
                activeLiveSearch=live
            End If
            Dim url=activeSearchUrl & "&offset=" & offset
            Dim data=Await GetJson(url,requestCancellation)
            If requestNumber<>searchGeneration OrElse IsDisposed Then Return
            generation+=1 : preview.Clear() : readMore.Enabled=False
            rows.Clear() : grid.Rows.Clear()
            For Each item As Object In CType(data("results"),System.Collections.IEnumerable)
                Dim row=CType(item,Dictionary(Of String,Object)) : rows.Add(row)
                Dim fileType=Convert.ToString(row("ext")).TrimStart("."c).ToUpperInvariant()
                If fileType="" Then fileType="File"
                grid.Rows.Add(row("name"),fileType,row("share"),row("state"),If(row.ContainsKey("open_url"),row("open_url"),row("unc_path")))
            Next
            info.Text=Convert.ToInt32(data("total")).ToString("N0") & If(live," filename matches ("," matches (") & activeSearchType & "); " & Convert.ToString(data("elapsed_ms")) & " ms"
            nextButton.Enabled=offset+20<Convert.ToInt32(data("total")) AndAlso rows.Count>0
            If rows.Count=0 Then preview.Text="No matching files in the current index. Content extraction may still be running."
            If data("warning") IsNot Nothing Then info.Text &= " (see preview note)" : preview.Text=Convert.ToString(data("warning")) & Environment.NewLine & preview.Text
            If Not live AndAlso useCurrentFilters AndAlso autoClearFilters.Checked Then ClearFilters()
        Catch ex As OperationCanceledException
            ' A newer query superseded this request.
        Catch ex As Exception
            If requestNumber<>searchGeneration OrElse IsDisposed Then Return
            info.Text="Search failed"
            If live Then
                info.Text="Live search unavailable; press Enter to retry." : Return
            End If
            If Environment.GetCommandLineArgs().Contains("--smoke") Then Throw
            MessageBox.Show(ex.Message,"Archive Search")
        Finally
            If requestNumber=searchGeneration AndAlso Not IsDisposed Then searchButton.Enabled=True
        End Try
    End Function
    Private Function Selected() As Dictionary(Of String,Object)
        If grid.CurrentRow Is Nothing OrElse grid.CurrentRow.Index<0 OrElse grid.CurrentRow.Index>=rows.Count Then Return Nothing
        Return rows(grid.CurrentRow.Index)
    End Function
    Private Function SelectedPath() As String
        Dim row=Selected()
        If row Is Nothing Then Return ""
        Return Convert.ToString(row("unc_path"))
    End Function
    Private Sub ShowInExplorer()
        Dim p=SelectedPath()
        If p="" Then Return
        Try
            Process.Start("explorer.exe","/select,""" & p & """")
        Catch ex As Exception
            MessageBox.Show(ex.Message,"Cannot open folder")
        End Try
    End Sub
    Private Sub OpenOriginal()
        Dim p=SelectedPath()
        Dim row=Selected()
        If row IsNot Nothing AndAlso row.ContainsKey("open_url") Then
            Dim target As Uri=Nothing
            If Not Uri.TryCreate(Convert.ToString(row("open_url")),UriKind.Absolute,target) OrElse (target.Scheme<>"http" AndAlso target.Scheme<>"https") Then Return
            p=target.AbsoluteUri
        End If
        If p="" Then Return
        Try
            Process.Start(New ProcessStartInfo(p) With {.UseShellExecute=True})
        Catch ex As Exception
            MessageBox.Show(ex.Message,"Cannot open original")
        End Try
    End Sub
    Private Async Function LoadPreview(off As Integer) As Task
        Dim row=Selected()
        If row Is Nothing Then Return
        generation+=1 : Dim request=generation
        Try
            Dim id=Uri.EscapeDataString(Convert.ToString(row("id")))
            Dim data=Await GetJson("/api/read/" & id & "?offset=" & off)
            If request<>generation Then Return
            preview.Text=Convert.ToString(data("unc_path")) & Environment.NewLine & Convert.ToString(data("metadata")) & Environment.NewLine & Environment.NewLine & Convert.ToString(data("text"))
            nextPreview=If(data("next_offset") Is Nothing,-1,Convert.ToInt32(data("next_offset")))
            readMore.Enabled=nextPreview>=0
        Catch ex As Exception
            If request=generation Then preview.Text="Preview unavailable: " & ex.Message
        End Try
    End Function
End Class

Public Module Program
    <STAThread> Public Sub Main()
        Application.EnableVisualStyles()
        Application.SetCompatibleTextRenderingDefault(False)
        Application.Run(New SearchWindow())
    End Sub
End Module
