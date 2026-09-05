# 外部工具目录

此目录存放运行时需要的外部可执行文件：
- `ffmpeg/ffmpeg.exe` — 视频处理工具（爬虫下载抖音/B站视频时合并音视频流）
- `Chrome/chrome.exe` — 便携版 Chrome（抖音爬虫扫码登录用，独立 Profile 防止污染用户日常浏览器）

## 打包发布时

绿色版（build_portable.py）和安装包（build_installer.iss）会**自动把整个 support/ 目录一起拷贝**到发布产物里，用户安装/解压后即可直接使用，无需再手动下载放入。

## 开发机准备

首次打包前，请在本目录下放好：
```
support/
├── ffmpeg/
│   └── ffmpeg.exe          # 从 https://www.gyan.dev/ffmpeg/builds/ 下载 Windows build
├── Chrome/
│   └── chrome.exe          # 便携版 Chrome 主程序
└── README.md               # 本文件
```

> `Chrome/Profile-Douyin/` 目录不需要提前创建，程序首次登录时会自动生成。
