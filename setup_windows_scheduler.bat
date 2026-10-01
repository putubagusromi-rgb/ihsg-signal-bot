@echo off
chcp 65001 >nul
echo ============================================================
echo   SETUP OTOMATIS PENJADWAL WINDOWS (IHSG SIGNAL BOT)
echo ============================================================
echo.

set PROJECT_DIR=%~dp0
set MORNING_SCRIPT=%PROJECT_DIR%run_morning.bat
set CLOSING_SCRIPT=%PROJECT_DIR%run_closing.bat

echo [1/2] Membuat Jadwal Morning Briefing (Senin-Jumat jam 08:30 WIB)...
schtasks /Create /TN "IHSG_Morning_Alert" /TR "\"%MORNING_SCRIPT%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 08:30 /F

echo [2/2] Membuat Jadwal Closing Report (Senin-Jumat jam 16:15 WIB)...
schtasks /Create /TN "IHSG_Closing_Alert" /TR "\"%CLOSING_SCRIPT%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:15 /F

echo.
echo ============================================================
echo  Jadwal otomatis Windows berhasil didaftarkan!
echo  Bot akan mengirim alert ke Telegram setiap hari bursa:
echo   - 08:30 WIB (Pagi sebelum buka bursa)
echo   - 16:15 WIB (Sore setelah tutup bursa)
echo ============================================================
echo.
pause
