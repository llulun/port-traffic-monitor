@echo off
chcp 65001 >nul
echo ==========================================
echo       主机端口流量监控 - 自动部署脚本
echo ==========================================
echo.

echo [1/3] 正在检查 Docker 环境...
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker 未运行或未安装！
    echo 请先启动 Docker Desktop，然后重新运行此脚本。
    echo.
    pause
    exit /b
)
echo Docker 运行正常。
echo.

echo [2/3] 正在构建 Docker 镜像...
docker build -t traffic-monitor .
if %errorlevel% neq 0 (
    echo [错误] 镜像构建失败！请检查上方错误信息。
    pause
    exit /b
)
echo 镜像构建成功！
echo.

echo [3/3] 正在上传代码到 GitHub...
echo 注意：如果这是第一次连接，可能会弹出窗口要求输入 GitHub 账号密码。
git push -u origin main
if %errorlevel% neq 0 (
    echo [错误] 代码上传失败！
    echo 可能原因：
    echo 1. 没有 GitHub 权限或密码错误
    echo 2. 网络连接问题
    echo.
    pause
    exit /b
)

echo.
echo ==========================================
echo           🎉 全部操作成功完成！
echo ==========================================
echo 1. 代码已同步至 GitHub
echo 2. Docker 镜像已在本地构建完成
echo 3. GitHub Actions 稍后将自动构建在线镜像
echo.
pause
