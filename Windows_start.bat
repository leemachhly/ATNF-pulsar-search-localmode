@echo off
rem 兼容旧入口：转到通用启动脚本 start.py
cd /d "%~dp0"
call "%~dp0start.bat" %*
