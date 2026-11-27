# NovaUploader

Nova3D 树脂 3D 打印机的第三方管理工具（Windows 桌面）。直接调用打印机固件自带的 HTTP 接口（端口 8081），不依赖官方 NovaMaker，也不需要联网或登录账号。

## 为什么有这个工具

NovaMaker 2.6.8 出现过「一点上传就卡死」的问题，排查后是系统级原因：**打开 Windows 原生文件对话框后，进程的 Winsock 会处于未初始化状态**，之后所有网络请求都会失败（`getaddrinfo` 报 `[Errno 10093]`）。NovaMaker 不会自愈，所以卡死后只能杀进程。

本工具直接绕开这条路径，并对上述问题做了自动修复（重新调用 `WSAStartup`），选完文件后网络依然正常。

## 功能

- **上传**：多选 `.cws`，实时进度条，失败原样提示
- **文件列表**：列出打印机上的文件（名称 / 大小 / 修改时间），可批量删除
- **打印状态**：实时层进度、已用与剩余时间、当前层曝光、层高、抬升参数
- **打印控制**：暂停 / 继续、停止、Z 轴升降、归位。打印进行中会自动锁定 Z 轴与归位，避免顶坏正在成型的件
- **打印历史**：按打印机（序列号）分组，长期留存，可查看每次的结束时间、用时、平均层时、层厚等参数
- **网络设置**：扫描并连接 WiFi，查看有线网卡状态。打印机无线出问题、改走网线直连时用得上
- **多打印机**：按序列号区分，下拉切换
- **完成通知**：打印结束弹出提醒并播放提示音，可开关

## 已测试设备

- Nova3D L3130-K40（固件 6.0.6）

其他 Nova3D 机型使用同一套 8081 接口，理论上通用。个别机型的 `Z 轴移动` 参数不是真实毫米值，可在配置里用 `lift_scale` 校准（校准方式见下）。

## 使用

1. 从 Release 下载 `NovaUploader.exe`，双击运行（不需要安装 Python）
2. 点「＋ 添加」，填入打印机 IP，点选即可连接
3. 上传：点「选择 .cws 文件」→「开始上传」
4. 打印控制、网络设置、打印历史都在主界面上直接操作

## 数据位置

配置与历史保存在 `%APPDATA%\NovaUploader\`，与程序目录分离，移动或重命名 exe 都不会丢：

```
%APPDATA%\NovaUploader\printers.json   打印机列表、Z 轴系数、上次目录
%APPDATA%\NovaUploader\history.json    打印历史
```

## 从源码运行与构建

```bash
python NovaUploader.py
```

打包成单文件 exe：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name NovaUploader NovaUploader.py
```

## Z 轴系数校准

如果点 `↑10` 后平台实际升高不是 10 mm，说明该机型的参数不是毫米单位。量出实际升高值 `H`，则：

```
lift_scale = H / 10
```

填进 `printers.json` 对应打印机的 `lift_scale` 字段，重启工具生效。默认 `1.0` 表示参数即毫米。

## 已知限制

- 固件不提供电机负载、Z 限位、温度等遥测数据，因此无法做硬件级的异常检测
- 部分机型的 `/job/getImg`（任务缩略图）固定返回 HTTP 500，无法显示打印预览
- `resinUsage` / `totalCost` 两个字段固件恒返回 0，不做用量与成本统计

## License

[MIT](LICENSE)
