# NovaCtl (Android) 构建脚本
# 不依赖 Gradle：直接用 aapt2 + javac + d8 + zipalign + apksigner
#
# 工具链默认放在 D:\AndroidDev，可用环境变量覆盖：
#   $env:ANDROID_TOOLCHAIN = "D:\AndroidDev"
# 需要的组件：jdk-17.0.21.1+2、android-14 (build-tools 34)、android-34-ext12 (platform)

$ErrorActionPreference = 'Stop'

$PROJ  = $PSScriptRoot
$REPO  = Split-Path $PROJ -Parent
$TOOLS = if ($env:ANDROID_TOOLCHAIN) { $env:ANDROID_TOOLCHAIN } else { "D:\AndroidDev" }

$JDK         = Join-Path $TOOLS "jdk-17.0.21.1+2"
$BT          = Join-Path $TOOLS "android-14"
$ANDROID_JAR = Join-Path $TOOLS "android-34-ext12\android.jar"
$OUT         = Join-Path $PROJ "build"
$KS          = Join-Path $PROJ "novactl.keystore"
$STOREPASS   = "novactl2026"
$APK_NAME    = "NovaCtl.apk"

foreach ($p in @($JDK, $BT, $ANDROID_JAR)) {
    if (-not (Test-Path $p)) { throw "找不到工具链组件：$p`n请设置 ANDROID_TOOLCHAIN 指向含 JDK / build-tools / platform 的目录" }
}

$env:JAVA_HOME = $JDK
$env:PATH = "$JDK\bin;$BT;$env:PATH"

function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }

# 原生程序失败时不要被 PowerShell 当成异常，统一用退出码判断
function RunNative($exe, $arguments, $label) {
    $log = Join-Path $OUT "native.log"
    $ErrorActionPreference = 'Continue'
    & $exe @arguments *> $log
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) {
        Write-Host "---- $label 输出 ----" -ForegroundColor Yellow
        if (Test-Path $log) { Get-Content $log -Encoding Default | ForEach-Object { Write-Host "  $_" } }
        throw "$label 失败 (exit $code)"
    }
}

Step "清理输出目录"
Remove-Item $OUT -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$OUT\gen", "$OUT\classes", "$OUT\dex" | Out-Null

Step "1/7 编译资源 (aapt2 compile)"
RunNative "$BT\aapt2.exe" @("compile", "--dir", "$PROJ\res", "-o", "$OUT\res.zip") "aapt2 compile"

Step "2/7 链接资源并生成 R.java (aapt2 link)"
RunNative "$BT\aapt2.exe" @("link", "-o", "$OUT\base.apk", "-I", $ANDROID_JAR,
    "--manifest", "$PROJ\AndroidManifest.xml", "-R", "$OUT\res.zip",
    "--java", "$OUT\gen", "--auto-add-overlay") "aapt2 link"

Step "3/7 编译 Java (javac)"
$srcs = @(Get-ChildItem "$PROJ\src" -Recurse -Filter *.java | ForEach-Object { $_.FullName })
$srcs += @(Get-ChildItem "$OUT\gen" -Recurse -Filter *.java | ForEach-Object { $_.FullName })
RunNative "$JDK\bin\javac.exe" (@("-nowarn", "-source", "8", "-target", "8",
    "-bootclasspath", $ANDROID_JAR, "-classpath", $ANDROID_JAR,
    "-encoding", "UTF-8", "-d", "$OUT\classes") + $srcs) "javac"

Step "4/7 打包 class 并转 dex (jar + d8)"
RunNative "$JDK\bin\jar.exe" @("cf", "$OUT\classes.jar", "-C", "$OUT\classes", ".") "jar"
RunNative "$BT\d8.bat" @("--lib", $ANDROID_JAR, "--min-api", "21",
    "--output", "$OUT\dex", "$OUT\classes.jar") "d8"

Step "5/7 把 classes.dex 合进 APK"
$merge = @"
import shutil, zipfile, sys
src, dex, dst = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.copyfile(src, dst)
with zipfile.ZipFile(dst, 'a', zipfile.ZIP_DEFLATED) as z:
    z.write(dex, 'classes.dex')
print('dex merged')
"@
$merge | Out-File -FilePath "$OUT\merge.py" -Encoding UTF8
python "$OUT\merge.py" "$OUT\base.apk" "$OUT\dex\classes.dex" "$OUT\unsigned.apk"
if ($LASTEXITCODE -ne 0) { throw "合并 dex 失败" }

Step "6/7 对齐 (zipalign)"
RunNative "$BT\zipalign.exe" @("-f", "-p", "4", "$OUT\unsigned.apk", "$OUT\aligned.apk") "zipalign"

Step "7/7 签名 (apksigner)"
if (-not (Test-Path $KS)) {
    RunNative "$JDK\bin\keytool.exe" @("-genkeypair", "-keystore", $KS,
        "-storepass", $STOREPASS, "-alias", "novactl", "-keypass", $STOREPASS,
        "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
        "-dname", "CN=NovaCtl, OU=Personal, O=Local, L=Local, ST=Local, C=CN") "keytool"
    Write-Host "    已生成签名密钥 $KS"
}
RunNative "$BT\apksigner.bat" @("sign", "--ks", $KS, "--ks-pass", "pass:$STOREPASS",
    "--key-pass", "pass:$STOREPASS", "--out", "$PROJ\$APK_NAME", "$OUT\aligned.apk") "apksigner sign"

$ErrorActionPreference = 'Continue'
& "$BT\apksigner.bat" verify --print-certs "$PROJ\$APK_NAME" *> "$OUT\verify.log"
$ErrorActionPreference = 'Stop'
Get-Content "$OUT\verify.log" -Encoding Default | Select-Object -First 3 | ForEach-Object { Write-Host "  $_" }

$apk = Get-Item "$PROJ\$APK_NAME"
Write-Host "`n构建完成: $($apk.FullName)" -ForegroundColor Green
Write-Host ("大小: {0:N0} KB" -f ($apk.Length / 1KB)) -ForegroundColor Green
