@echo off
chcp 65001 >nul
title 星露谷小鸡桌宠 - 一键安装

echo.
echo   ╔══════════════════════════════════╗
echo   ║    🐤 星露谷小鸡桌宠 - 安装向导   ║
echo   ╚══════════════════════════════════╝
echo.

:: ── 1. 找到 Python ──────────────────────────
echo [1/4] 正在检测 Python...
set PYTHON=
set PYTHONW=

:: 尝试常见路径
for %%p in (python python3) do (
    where %%p >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('where %%p 2^>nul') do set "PYTHON=%%i"
        goto :found_python
    )
)

:: 尝试在常见安装位置寻找
for %%d in (
    "%LOCALAPPDATA%\Programs\Python\Python313"
    "%LOCALAPPDATA%\Programs\Python\Python312"
    "%LOCALAPPDATA%\Programs\Python\Python311"
    "%LOCALAPPDATA%\Programs\Python\Python310"
    "%LOCALAPPDATA%\Programs\Python\Python39"
    "%LOCALAPPDATA%\Programs\Python\Python38"
    "%LOCALAPPDATA%\Programs\Python\Python37"
    "%PROGRAMFILES%\Python313"
    "%PROGRAMFILES%\Python312"
    "%PROGRAMFILES%\Python311"
) do (
    if exist "%%d\python.exe" (
        set "PYTHON=%%d\python.exe"
        goto :found_python
    )
)

echo [错误] 未找到 Python！请先安装 Python 3.7+
echo        下载地址: https://www.python.org/downloads/
pause
exit /b 1

:found_python
echo       找到: %PYTHON%

:: 推导 pythonw 路径
for %%f in ("%PYTHON%") do set "PYTHON_DIR=%%~dpf"
set "PYTHONW=%PYTHON_DIR%pythonw.exe"
if exist "%PYTHONW%" (
    echo       pythonw: %PYTHONW%
) else (
    echo [警告] 未找到 pythonw.exe，将使用 python.exe（会有控制台窗口）
    set "PYTHONW=%PYTHON%"
)

:: ── 2. 安装依赖 ──────────────────────────────
echo.
echo [2/4] 正在安装依赖 (PyQt5)...
"%PYTHON%" -m pip install PyQt5 --quiet
if errorlevel 1 (
    echo [警告] PyQt5 安装失败，请手动运行: pip install PyQt5
) else (
    echo       PyQt5 安装完成 ✅
)

:: ── 3. 创建桌面快捷方式 ──────────────────────
echo.
echo [3/4] 正在创建桌面快捷方式...

set "PROJECT_DIR=%~dp0"
set "ICON_PATH=%PROJECT_DIR%assets\white_chicken.ico"

:: 用 PowerShell 创建快捷方式
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
  $desktop = [Environment]::GetFolderPath('Desktop'); ^
  $lnk = $ws.CreateShortcut(\"$desktop\星露谷小鸡桌宠.lnk\"); ^
  $lnk.TargetPath = '%PYTHONW%'; ^
  $lnk.Arguments = '-m src.main'; ^
  $lnk.WorkingDirectory = '%PROJECT_DIR%'; ^
  $lnk.IconLocation = '%ICON_PATH%'; ^
  $lnk.Description = '星露谷小鸡桌宠 - 双击启动'; ^
  $lnk.WindowStyle = 7; ^
  $lnk.Save(); ^
  Write-Host '快捷方式已创建'"

if errorlevel 1 (
    echo [警告] 快捷方式创建失败，你可以手动创建
) else (
    echo       桌面快捷方式创建完成 ✅
)

:: ── 4. 完成 ──────────────────────────────────
echo.
echo [4/4] 安装完成！
echo.
echo   ╔═══════════════════════════════════════╗
echo   ║  🎉 星露谷小鸡桌宠 安装成功！        ║
echo   ║                                       ║
echo   ║  双击桌面的「星露谷小鸡桌宠」即可     ║
echo   ║  在桌面上见到你的小鸡啦 🐤            ║
echo   ╚═══════════════════════════════════════╝
echo.
echo   小提示: 右键系统托盘图标可以打开菜单哦~
echo.

pause
