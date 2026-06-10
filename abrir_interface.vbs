Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python311\pythonw.exe"
command = """" & pythonw & """ -m automacao_correcao.gui"
shell.CurrentDirectory = base
shell.Run command, 0, False
