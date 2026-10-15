echo off
set LOCALHOST=%COMPUTERNAME%
set KILL_CMD="F:\Program Files\ANSYS Inc\v242\fluent/ntbin/win64/winkill.exe"

start "tell.exe" /B "F:\Program Files\ANSYS Inc\v242\fluent\ntbin\win64\tell.exe" zper 58067 CLEANUP_EXITING
timeout /t 1
"F:\Program Files\ANSYS Inc\v242\fluent\ntbin\win64\kill.exe" tell.exe
if /i "%LOCALHOST%"=="zper" (%KILL_CMD% 4400) 
if /i "%LOCALHOST%"=="zper" (%KILL_CMD% 31492) 
if /i "%LOCALHOST%"=="zper" (%KILL_CMD% 42472)
del "C:\Users\zpern\Desktop\todo\jiuyuan-quailty\internal\cleanup-fluent-zper-31492.bat"
