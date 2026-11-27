' NovaUploader launcher
' Runs NovaUploader.py with pythonw.exe so no console window appears.
Dim fso, shell, dir, py
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
py = "C:\Python314\pythonw.exe"
If Not fso.FileExists(py) Then py = "pythonw.exe"

shell.CurrentDirectory = dir
shell.Run """" & py & """ """ & dir & "\NovaUploader.py""", 0, False
