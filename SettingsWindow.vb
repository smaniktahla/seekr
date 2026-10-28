Imports System
Imports System.Collections.Generic
Imports System.Drawing
Imports System.Net.Http
Imports System.Net.Http.Headers
Imports System.Text
Imports System.Threading.Tasks
Imports System.Web.Script.Serialization
Imports System.Windows.Forms

Public Class SettingsWindow
    Inherits Form
    Private ReadOnly serviceUrlBox As New TextBox()
    Private ReadOnly tokenBox As New TextBox With {.UseSystemPasswordChar=True}
    Private ReadOnly folders As New DataGridView()
    Private ReadOnly duplicateBox As New CheckBox With {.Text="Hide exact duplicate files (SHA-256)",.AutoSize=True}
    Private ReadOnly docmostBox As New CheckBox With {.Text="Include DocMost in full-text searches",.AutoSize=True}
    Private ReadOnly mcpBox As New TextBox()
    Private ReadOnly semanticBox As New TextBox()
    Private ReadOnly appBox As New TextBox()
    Private ReadOnly linkBox As New TextBox()
    Private ReadOnly saveButton As New Button With {.Text="Save",.AutoSize=True,.Enabled=False}
    Private ReadOnly loadButton As New Button With {.Text="Load service settings",.AutoSize=True}
    Private ReadOnly statusLabel As New Label With {.AutoSize=True}
    Private ReadOnly serializer As New JavaScriptSerializer()
    Private ReadOnly currentToken As String
    Private loadedUrl As String = Nothing
    Public Property Configuration As Dictionary(Of String,Object)
    Public ReadOnly Property ServiceUrl As String
        Get
            Return serviceUrlBox.Text.Trim().TrimEnd("/"c)
        End Get
    End Property
    Public ReadOnly Property Token As String
        Get
            Return If(String.IsNullOrWhiteSpace(tokenBox.Text),currentToken,tokenBox.Text.Trim())
        End Get
    End Property

    Public Sub New(url As String,token As String,nasUrl As String)
        Text="Seekr Settings" : Size=New Size(960,650) : MinimumSize=New Size(760,560)
        Font=New Font("Segoe UI",10) : StartPosition=FormStartPosition.CenterParent
        currentToken=token
        Dim root As New TableLayoutPanel With {.Dock=DockStyle.Fill,.RowCount=3,.ColumnCount=1,.Padding=New Padding(15)}
        root.RowStyles.Add(New RowStyle(SizeType.Absolute,120)) : root.RowStyles.Add(New RowStyle(SizeType.Percent,100)) : root.RowStyles.Add(New RowStyle(SizeType.Absolute,50))
        Dim connection As New TableLayoutPanel With {.Dock=DockStyle.Fill,.ColumnCount=2,.RowCount=3}
        connection.ColumnStyles.Add(New ColumnStyle(SizeType.Absolute,150)) : connection.ColumnStyles.Add(New ColumnStyle(SizeType.Percent,100))
        serviceUrlBox.Text=url : serviceUrlBox.AccessibleName="Search service URL"
        AddField(connection,0,"Search service URL",serviceUrlBox)
        tokenBox.AccessibleName="Service token (blank keeps current)" : AddField(connection,1,"Token (optional)",tokenBox)
        Dim controls As New FlowLayoutPanel With {.Dock=DockStyle.Fill}
        Dim localButton As New Button With {.Text="Use local",.AutoSize=True}
        Dim nasButton As New Button With {.Text="Use NAS",.AutoSize=True}
        controls.Controls.AddRange(New Control(){loadButton,localButton,nasButton})
        connection.Controls.Add(controls,1,2) : root.Controls.Add(connection,0,0)
        AddHandler localButton.Click, Sub(s,e) serviceUrlBox.Text="http://127.0.0.1:8093"
        AddHandler nasButton.Click, Sub(s,e) serviceUrlBox.Text=nasUrl
        AddHandler serviceUrlBox.TextChanged, Sub(s,e) saveButton.Enabled=False
        Dim tabs As New TabControl With {.Dock=DockStyle.Fill}
        Dim folderTab As New TabPage("Index folders")
        Dim folderLayout As New TableLayoutPanel With {.Dock=DockStyle.Fill,.RowCount=3,.ColumnCount=1,.Padding=New Padding(8)}
        folderLayout.RowStyles.Add(New RowStyle(SizeType.Absolute,62)) : folderLayout.RowStyles.Add(New RowStyle(SizeType.Percent,100)) : folderLayout.RowStyles.Add(New RowStyle(SizeType.Absolute,40))
        folderLayout.Controls.Add(New Label With {.Text="Server folder = a path accessible to the selected service. For a NAS container, add a read-only bind mount before using a new folder. Open path = its Windows folder or SMB path. Untick Enabled to hide a source without deleting originals.",.Dock=DockStyle.Fill},0,0)
        folders.Dock=DockStyle.Fill : folders.AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill : folders.RowHeadersVisible=False
        folders.Columns.Add("Id","Folder ID") : folders.Columns(0).FillWeight=16
        folders.Columns.Add("Path","Server folder") : folders.Columns(1).FillWeight=35
        folders.Columns.Add("Client","Open path (Windows / SMB)") : folders.Columns(2).FillWeight=35
        folders.Columns.Add(New DataGridViewCheckBoxColumn With {.Name="Enabled",.HeaderText="Enabled",.FillWeight=14,.TrueValue=True,.FalseValue=False})
        folderLayout.Controls.Add(folders,0,1)
        Dim folderButtons As New FlowLayoutPanel With {.Dock=DockStyle.Fill}
        Dim browse As New Button With {.Text="Add local folder...",.AutoSize=True}
        Dim remove As New Button With {.Text="Remove selected source",.AutoSize=True}
        folderButtons.Controls.AddRange(New Control(){browse,remove}) : folderLayout.Controls.Add(folderButtons,0,2)
        AddHandler browse.Click, Sub(s,e)
            Dim target As Uri=Nothing
            If Not Uri.TryCreate(ServiceUrl,UriKind.Absolute,target) OrElse Not target.IsLoopback Then
                MessageBox.Show("Folder browsing applies to a service running on this computer. For a NAS service, enter a NAS-side folder and its Windows/SMB open path.","Index folders") : Return
            End If
            Using dialog As New FolderBrowserDialog()
                If dialog.ShowDialog(Me)=DialogResult.OK Then folders.Rows.Add("Local" & folders.Rows.Count,dialog.SelectedPath,dialog.SelectedPath,True)
            End Using
        End Sub
        AddHandler remove.Click, Sub(s,e)
            If folders.CurrentRow IsNot Nothing AndAlso Not folders.CurrentRow.IsNewRow Then folders.Rows.Remove(folders.CurrentRow)
        End Sub
        folderTab.Controls.Add(folderLayout) : tabs.TabPages.Add(folderTab)
        Dim duplicateTab As New TabPage("Duplicates")
        Dim duplicateLayout As New FlowLayoutPanel With {.Dock=DockStyle.Fill,.FlowDirection=FlowDirection.TopDown,.Padding=New Padding(15)}
        duplicateLayout.Controls.Add(duplicateBox)
        duplicateLayout.Controls.Add(New Label With {.Text="Only byte-for-byte identical files are grouped. Filename and size alone never hide a file. Originals are never deleted. Untick this option to show every copy.",.AutoSize=False,.Size=New Size(650,65)})
        duplicateLayout.Controls.Add(New Label With {.Text="Background hashing checks files with matching sizes. Files awaiting a verified hash remain visible; grouping improves as hashing catches up. Large duplicate candidates can take time to read.",.AutoSize=False,.Size=New Size(650,65)})
        duplicateTab.Controls.Add(duplicateLayout) : tabs.TabPages.Add(duplicateTab)
        Dim dmTab As New TabPage("DocMost")
        Dim dmLayout As New TableLayoutPanel With {.Dock=DockStyle.Fill,.ColumnCount=2,.RowCount=7,.Padding=New Padding(10)}
        dmLayout.ColumnStyles.Add(New ColumnStyle(SizeType.Absolute,180)) : dmLayout.ColumnStyles.Add(New ColumnStyle(SizeType.Percent,100))
        For i As Integer=0 To 4
            dmLayout.RowStyles.Add(New RowStyle(SizeType.Absolute,40))
        Next
        dmLayout.RowStyles.Add(New RowStyle(SizeType.Percent,60)) : dmLayout.RowStyles.Add(New RowStyle(SizeType.Percent,40))
        dmLayout.Controls.Add(docmostBox,1,0)
        AddField(dmLayout,1,"MCP endpoint",mcpBox) : AddField(dmLayout,2,"Semantic API base URL",semanticBox)
        AddField(dmLayout,3,"DocMost app URL",appBox) : AddField(dmLayout,4,"Page URL template",linkBox)
        dmLayout.Controls.Add(New Label With {.Text="Read-only: search_notes and get_note only. No database writes or credentials are needed for the existing LAN endpoints. Semantic results follow DocMost's ingestion schedule. Typing searches files; Enter includes DocMost. Up to 20 DocMost notes are included per query.",.Dock=DockStyle.Fill},1,5)
        dmLayout.Controls.Add(New Label With {.Text="Optional page URL template must contain {id}. Without it, Open launches the DocMost app; the note is still readable in Seekr's preview.",.Dock=DockStyle.Fill},1,6)
        dmTab.Controls.Add(dmLayout) : tabs.TabPages.Add(dmTab) : root.Controls.Add(tabs,0,1)
        Dim footer As New FlowLayoutPanel With {.Dock=DockStyle.Fill}
        Dim cancel As New Button With {.Text="Cancel",.DialogResult=DialogResult.Cancel,.AutoSize=True}
        footer.Controls.AddRange(New Control(){saveButton,cancel,statusLabel}) : root.Controls.Add(footer,0,2)
        Me.Controls.Add(root) : CancelButton=cancel
        AddHandler loadButton.Click, Async Sub(s,e) Await LoadConfiguration()
        AddHandler saveButton.Click, Async Sub(s,e) Await SaveConfiguration()
        AddHandler Shown, Async Sub(s,e) Await LoadConfiguration()
    End Sub

    Private Shared Sub AddField(table As TableLayoutPanel,row As Integer,title As String,box As TextBox)
        table.Controls.Add(New Label With {.Text=title,.AutoSize=True,.Padding=New Padding(0,5,0,0)},0,row)
        box.Dock=DockStyle.Fill : box.AccessibleName=title : table.Controls.Add(box,1,row)
    End Sub
    Private Async Function Request(method As HttpMethod,path As String,Optional payload As Object=Nothing) As Task(Of Dictionary(Of String,Object))
        Dim target As Uri=Nothing
        If Not Uri.TryCreate(ServiceUrl,UriKind.Absolute,target) OrElse (target.Scheme<>"http" AndAlso target.Scheme<>"https") OrElse target.UserInfo<>"" Then Throw New Exception("Enter an HTTP(S) service URL without credentials.")
        Using client As New HttpClient(New HttpClientHandler With {.UseProxy=False})
            client.Timeout=TimeSpan.FromSeconds(20) : client.DefaultRequestHeaders.Authorization=New AuthenticationHeaderValue("Bearer",Token)
            Using message As New HttpRequestMessage(method,ServiceUrl & path)
                If payload IsNot Nothing Then message.Content=New StringContent(serializer.Serialize(payload),Encoding.UTF8,"application/json")
                Dim response=Await client.SendAsync(message)
                Dim body=Await response.Content.ReadAsStringAsync()
                If Not response.IsSuccessStatusCode Then
                    If CInt(response.StatusCode)=404 Then Throw New Exception("This service needs the Seekr settings backend update before it can be configured here.")
                    Dim detail="Service rejected settings (HTTP " & CInt(response.StatusCode) & ")."
                    Try
                        Dim errorData=serializer.Deserialize(Of Dictionary(Of String,Object))(body)
                        If errorData.ContainsKey("detail") Then detail=Convert.ToString(errorData("detail"))
                    Catch
                    End Try
                    Throw New Exception(detail)
                End If
                Return serializer.Deserialize(Of Dictionary(Of String,Object))(body)
            End Using
        End Using
    End Function
    Private Async Function LoadConfiguration() As Task
        loadButton.Enabled=False : saveButton.Enabled=False : statusLabel.Text="Loading..."
        Try
            Dim result=Await Request(HttpMethod.Get,"/api/settings")
            folders.Rows.Clear()
            For Each value As Object In CType(result("sources"),System.Collections.IEnumerable)
                Dim source=CType(value,Dictionary(Of String,Object))
                folders.Rows.Add(source("id"),source("path"),source("client_path"),source("enabled"))
            Next
            duplicateBox.Checked=Convert.ToBoolean(CType(result("dedupe"),Dictionary(Of String,Object))("enabled"))
            Dim dm=CType(result("docmost"),Dictionary(Of String,Object))
            docmostBox.Checked=Convert.ToBoolean(dm("enabled"))
            mcpBox.Text=Convert.ToString(dm("mcp_url")) : semanticBox.Text=Convert.ToString(dm("semantic_url"))
            appBox.Text=Convert.ToString(dm("app_url")) : linkBox.Text=Convert.ToString(dm("page_url_template"))
            loadedUrl=ServiceUrl : saveButton.Enabled=True : statusLabel.Text="Loaded. Save queues an incremental rescan."
        Catch ex As Exception
            statusLabel.Text="Could not load settings" : MessageBox.Show(ex.Message,"Seekr settings")
        Finally
            loadButton.Enabled=True
        End Try
    End Function
    Private Async Function SaveConfiguration() As Task
        If loadedUrl<>ServiceUrl Then MessageBox.Show("Load settings for this service before saving.","Seekr settings") : Return
        saveButton.Enabled=False
        Try
            folders.EndEdit()
            Dim items As New List(Of Object)()
            For Each row As DataGridViewRow In folders.Rows
                If row.IsNewRow Then Continue For
                items.Add(New Dictionary(Of String,Object) From {{"id",Convert.ToString(row.Cells(0).Value)},{"path",Convert.ToString(row.Cells(1).Value)},{"client_path",Convert.ToString(row.Cells(2).Value)},{"enabled",Convert.ToBoolean(If(row.Cells(3).Value,False))}})
            Next
            Dim config As New Dictionary(Of String,Object) From {{"sources",items},{"dedupe",New Dictionary(Of String,Object) From {{"enabled",duplicateBox.Checked}}},{"docmost",New Dictionary(Of String,Object) From {{"enabled",docmostBox.Checked},{"mcp_url",mcpBox.Text},{"semantic_url",semanticBox.Text},{"app_url",appBox.Text},{"page_url_template",linkBox.Text}}}}
            Configuration=Await Request(HttpMethod.Put,"/api/settings",config)
            DialogResult=DialogResult.OK : Close()
        Catch ex As Exception
            MessageBox.Show(ex.Message,"Could not save settings") : saveButton.Enabled=True
        End Try
    End Function
End Class
