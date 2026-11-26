[Setup]
AppId=BizAgent.Desktop
AppName=БизнесПомощник
AppVersion=2.0.0
DefaultDirName={localappdata}\Programs\BizAgent
DefaultGroupName=БизнесПомощник
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=BizAgent-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Excludes: "pgsql\include\*,*\__pycache__\*,*\.pytest_cache\*,bizagent\tests\*,python\site-packages\pip\*,python\site-packages\setuptools\*"; Flags: recursesubdirs createallsubdirs ignoreversion
[Icons]
Name: "{group}\БизнесПомощник"; Filename: "{app}\python\python.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"
Name: "{autodesktop}\БизнесПомощник"; Filename: "{app}\python\python.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"
[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\launcher.py"""; Description: "Открыть БизнесПомощник"; Flags: postinstall nowait skipifsilent
