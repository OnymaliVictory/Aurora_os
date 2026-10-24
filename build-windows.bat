@echo off
REM Build Aurora OS on a Windows computer that has Python 3.11+ installed.
python -m venv .venv || goto :err
call .venv\Scripts\activate
pip install -r requirements.txt pyinstaller pytest || goto :err
python -m pytest tests -q || goto :err
pyinstaller build\aurora_os.spec --noconfirm || goto :err
echo.
echo DONE. Your program is in dist\AuroraOS\AuroraOS.exe
echo For a proper installer, open build\installer.iss in Inno Setup and press Compile.
pause & exit /b 0
:err
echo Something failed - read the messages above.
pause & exit /b 1
