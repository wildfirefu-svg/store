@echo off
chcp 65001 >nul
cd /d "C:\Users\Administrator\Desktop\agent"

echo ========================================
echo   八字命理分析报告 PDF 生成器
echo ========================================
echo.

REM Check available templates
echo 可用模板:
echo   1. dark    - 经典暗金（默认）
echo   2. modern  - 清新现代
echo   3. scroll  - 古风卷轴（推荐用于深度分析）
echo   4. night   - 暗夜模式
echo.

set /p tpl="选择模板 (1-4, 直接回车=scroll): "

if "%tpl%"=="1" set tplname=dark
if "%tpl%"=="2" set tplname=modern
if "%tpl%"=="3" set tplname=scroll
if "%tpl%"=="4" set tplname=night
if "%tpl%"=="" set tplname=scroll

echo.
echo 正在生成 PDF (模板: %tplname%) ...
echo.

python report_to_pdf.py "reports/命主_1963-07-09/四合出_四派综合分析报告.md" -o "reports/命主_1963-07-09/四合出_四派综合分析报告.pdf" --template %tplname%

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   PDF 生成成功!
    echo   文件: reports/命主_1963-07-09/四合出_四派综合分析报告.pdf
    echo   模板: %tplname%
    echo ========================================
) else (
    echo.
    echo PDF 生成失败，请检查:
    echo   1. Python 是否已安装 (python --version)
    echo   2. fpdf 库是否已安装 (python -c "from fpdf import FPDF")
    echo   3. Markdown 文件是否存在
)

echo.
pause
