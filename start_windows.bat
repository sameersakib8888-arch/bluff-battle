@echo off
cd /d "%~dp0"
echo Installing BLUFF BATTLE dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo =================================================
echo BLUFF BATTLE is ready at http://localhost:8080
 echo Share your computer's LAN IP for Wi-Fi play.
echo =================================================
py server.py
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Could not start the game. Make sure Python 3.10+ is installed.
echo See README.md for help.
pause
exit /b 1
