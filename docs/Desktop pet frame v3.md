# 净无欲-王涵桌面电子宠物

## 1.项目简介

这是一个基于 *《美女，请别影响我成仙》* 中师傅净无欲（王涵）的高自由度电脑（WINDOWS）桌面电子宠物。

***

## 2.核心功能模块

### 2.1 基础模块

| 功能名称  | 功能描述                                    | 实现状态 | 扩展预留              |
| ----- | --------------------------------------- | ---- | ----------------- |
| 透明窗口  | 无边框，背景全透明，宠物悬浮于桌面之上                     | 已实现  | 可扩展窗口置顶/置底、窗口大小调整 |
| 多状态动画 | 包含待机、行走、睡觉、玩耍、生气等多种状态，随机触发             | 已实现  | 可扩展更多状态         |
| 自由拖拽  | 支持鼠标左键拖拽宠物到桌面任意位置，拖动中进入被拖动状态，松开后有"松开"动画 | 已实现  | 可扩展拖拽时的视觉反馈、拖拽音效  |
| 窗口置顶  | 宠物窗口始终显示在最上层                            | 已实现  | 可扩展窗口层级管理         |
| 自动隐藏  | 宠物靠近屏幕边缘时自动隐藏                           | 待扩展  | 可扩展边缘吸附、自动弹出      |
| 首次启动免责声明 | 滚动到底 + 倒计时后才能勾选继续，记录到 `data/consent.json`      | 已实现（v1.4） | 条款更新 bump `CONSENT_VERSION` 强制重新同意 |

### 2.2 高级模块（偏向交互互动）

*暂定鼠标右键菜单显示与左键点击选择使用各功能*

| 功能名称 | 功能描述                   | 实现状态 | 扩展预留             |
| ---- | ---------------------- | ---- | ---------------- |
| 吃东西  | "吃猪蹄"动画，后丢给用户"骨头"图片    | 已实现  | 可扩展更多食物类型、吃东西音效  |
| 求投喂  | 让用户投喂"葡萄汁"图片（会刷出来给用户的） | 已实现  | 可扩展更多投喂物品、投喂反馈   |
| 喂食   | 喂用户豆腐，给用户"豆腐"图片        | 已实现  | 可扩展更多喂食物品、喂食效果   |
| 交互反馈 | 点击宠物时给出表情或动作反馈         | 已实现  | 可扩展触摸反馈、语音反馈     |
| 情绪系统 | 宠物拥有情绪值，影响行为表现         | 待扩展  | 可扩展情绪影响动画、情绪影响交互 |
| 更多功能 | 待扩展                    | 未规划  | 可添加：摸头、对话、小游戏等   |

### 2.3 拓展模块 *（算DLC？）*

| 功能名称         | 功能描述                                                                    | 实现状态 | 扩展预留                                                                  |
| ------------ | ----------------------------------------------------------------------- | ---- | --------------------------------------------------------------------- |
| B站爬虫         | 爬取王涵最新视频（Selenium + WBI 签名接口兜底，支持多 XPATH 回退 + 便携 Chrome 复用 Cookie）                | 已集成  | 可扩展视频下载、自动播放、视频列表管理、推送通知                                           |
| 抖音爬虫         | 爬取王涵抖音最新视频（**首次扫码登录 → Profile 目录持久化 + Cookie 双快照**；列表走 Selenium，下载交给 yt-dlp 带签名） | 已集成（含置顶/登录循环修复） | 可扩展定时爬取、直播提醒；需要用户在菜单里先做过一次「登录/重新登录（扫码）」                    |
| ihan 粉丝站彩蛋    | 菜单「关于此项目 → ihan 粉丝站 ✨」一键跳转，默认系统浏览器打开粉丝站                                        | 已集成  | 可扩展定时访问、页面截图、内容监控、签到自动化（待实现）                                                  |
| 浏览器自动访问      | 自动访问 ihan / 外链等（使用 support/ 下自带的便携版 Chrome + 独立用户资料目录，避免污染用户日常 Chrome 配置）       | 骨架已有 | 可扩展定时访问、页面截图、内容监控、定时签到                                                         |
| 更多拓展         | 待扩展                                                                    | 未规划  | 可添加：微博动态、直播提醒、日程提醒、ihan 帖子互动、B站/抖音更新推送通知                                          |

***

## 3.FSM状态机设计

### 3.1 状态定义表

| 状态名称 | 状态代码          | 状态描述              | 是否可被打断 | 扩展预留          |
| ---- | ------------- | ----------------- | ------ | ------------- |
| 待机   | `IDLE`        | 宠物静止站立，无动作        | 是      | -             |
| 行走   | `WALKING`     | 宠物在桌面上随机走动        | 是      | -             |
| 被拖拽  | `DRAGGING`    | 用户按住左键拖动宠物        | 否      | -             |
| 吃东西  | `EATING`      | 播放吃猪蹄动画           | 否      | -             |
| 求投喂  | `ASKING_FOOD` | 宠物做出期待的表情，刷出葡萄汁图片 | 是      | -             |
| 喂食   | `FEEDING`     | 用户投喂后宠物吃东西，然后吐出豆腐 | 否      | -             |
| 松开   | `RELEASED`    | 拖拽结束后播放的过渡动画      | 是      | -             |
| 睡觉   | `SLEEPING`    | 宠物进入睡眠状态          | 是      | 已使用          |
| 玩耍   | `PLAYING`     | 宠物玩耍状态            | 是      | 已使用          |
| 生气   | `ANGRY`       | 宠物生气状态            | 是      | 已使用          |
| 更多状态 | 待扩展           | -                 | -      | 可添加：洗澡、生病、开心等 |

### 3.2 状态转换条件表

| 当前状态         | 触发条件               | 目标状态         | 扩展预留        |
| ------------ | ------------------ | ------------ | ----------- |
| IDLE         | 随机触发（如每隔30秒）       | WALKING      | -           |
| IDLE         | 用户右键选择"吃东西"        | EATING       | -           |
| IDLE         | 用户右键选择"求投喂"        | ASKING\_FOOD | -           |
| IDLE         | 用户左键按住宠物（移动距离>5像素） | DRAGGING     | -           |
| IDLE         | 长时间未互动（如5分钟）       | SLEEPING     | 已使用         |
| WALKING      | 到达屏幕边界             | IDLE         | -           |
| WALKING      | 用户左键按住宠物           | DRAGGING     | -           |
| WALKING      | 随机停止               | IDLE         | -           |
| DRAGGING     | 用户松开左键             | RELEASED     | -           |
| RELEASED     | 动画播放完毕             | IDLE         | -           |
| EATING       | 动画播放完毕             | IDLE         | -           |
| ASKING\_FOOD | 用户点击葡萄汁图片          | FEEDING      | -           |
| ASKING\_FOOD | 超时未投喂（如10秒）        | IDLE         | -           |
| FEEDING      | 动画播放完毕             | IDLE         | -           |
| SLEEPING     | 用户点击宠物             | IDLE         | 已使用         |
| SLEEPING     | 睡眠时间结束             | IDLE         | 已使用         |
| PLAYING      | 玩耍时间结束             | IDLE         | 已使用         |
| ANGRY        | 用户安抚               | IDLE         | 已使用         |
| 更多转换         | 待扩展                | -            | 可添加新状态的转换规则 |

### 3.3 动画帧映射表（素材目录+映射已实现为单文件映射）

> **素材基准尺寸（以 `试.png 306×372 = 3:4 竖图` 为统一比例）**：
> 所有人物 GIF / PNG 原始制作按 **宽:高 = 3:4**（典型：360×480 或 480×640）。
> 程序运行时 `PET_HEIGHT = 240`，**自动按高度等比缩放为 180×240**，保证所有动作切换时窗口不跳动。
> 物品图统一按 `ITEM_HEIGHT = 80` 自动等比缩放。
> 素材制作时达芬奇里只需**裁紧人物**，不用手调比例；`frames_to_gif.py --size 360x480` 会补齐到统一框。

| 状态           | 素材文件（`ASSET_MAP` 键值）        | 类型 | 建议帧率 | 说明                  | 扩展预留   |
| ------------ | -------------------------- | -- | ---- | ------------------- | ------ |
| IDLE         | `试.gif` → 后续替换 `王涵_idle.gif`  | gif | 6-10 | 呼吸、眨眼等小动作           | -      |
| WALKING      | `试.gif` → `王涵_walking.gif`      | gif | 12-15 | 左右腿交替行走             | -      |
| DRAGGING     | `试.png` → `王涵_dragging.png`     | png | - | 静态图片，显示被抓住的样子       | -      |
| RELEASED     | `试.gif` → `王涵_released.gif`     | gif | 15 | 落地缓冲动画              | -      |
| EATING       | `试.gif` → `王涵_eating.gif`       | gif | 20 | 吃猪蹄的完整动作            | -      |
| ASKING\_FOOD | `试.gif` → `王涵_asking_food.gif`  | gif | 12 | 期待、招手等动作            | -      |
| FEEDING      | `试.gif` → `王涵_feeding.gif`      | gif | 20 | 吃东西然后吐出豆腐           | -      |
| SLEEPING     | `试.gif` → `王涵_sleeping.gif`     | gif | 5 | 睡眠呼吸动画              | 已使用    |
| PLAYING      | `试.gif` → `王涵_playing.gif`      | gif | 15 | 玩耍动作                | 已使用    |
| ANGRY        | `试.gif` → `王涵_angry.gif`        | gif | 12 | 生气表情和动作             | 已使用    |
| 物品（骨头/豆腐/葡萄汁） | `试_物品东西.png` → 各物品单独 PNG      | png | - | 葡萄汁横向约 160×120，缩到 **高 80px** | 已使用 |

***

## 4.交互方式设计

### 4.1 右键菜单结构（v3 最终：以代码实现为准）

```
右键点击宠物
├── 吃东西
│   └── 播放吃猪蹄动画，结束后在桌面显示骨头图片
├── 求投喂
│   └── 宠物进入求投喂状态，在宠物附近刷出葡萄汁图片
├── 喂食
│   └── 播放喂食动画，结束后在桌面显示豆腐图片
├── 拓展功能 ▶
│   ├── 爬取B站最新视频
│   ├── 抖音 ▶
│   │   ├── 爬取抖音最新视频
│   │   ├── 登录/重新登录（扫码）
│   │   └── 清除登录数据（退出登录）
│   ├── 代理设置…                     （HTTP / SOCKS5h + 可选鉴权，抖音/B 站爬虫使用）
│   ├── 清除隐私数据…                  （勾选删除代理/抖音登录/data/settings.json 等，带二次确认）
│   ├── 打开 data 目录
│   └── 打开 output 目录
├── 设置 ▶
│   ├── ☑ 窗口置顶                    （默认开，可关；立刻生效 + 写入 data/settings.json）
│   ├── 调整宠物大小…                 （高度 120~480 px，提供 180 / 240默认 / 320 三档预设，物品高度自动联动 1/3）
│   └── 恢复默认设置                   （一键重置「置顶=开 / 高度=240」，二次确认不碰爬虫数据）
├── 关于此项目 ▶
│   ├── GitHub
│   ├── Gitee
│   └── ihan 粉丝站 ✨（彩蛋，浏览器打开 ihan.com.cn）
└── 退出
    └── 关闭程序
```

> v3 说明：「摸头 / 对话 / 更多设置（待扩展）」在菜单里暂时没写占位 action，留到素材到位后按需扩；「代理设置」从 §4 老设计"挂在设置子菜单里"调整为"挂在拓展功能下"，因为代理是爬虫场景专用，不属于通用显示设置。

### 4.2 左键交互：点击 vs 拖拽的区分机制

**问题描述**：用户按下左键时，无法判断是想点击还是拖拽。

**解决方案**：添加移动距离阈值判定（阈值：5像素）

```
用户按下左键（记录起始位置）
    ↓
用户移动鼠标
    ↓
移动距离 < 5像素？
    ├── 是 → 视为点击（不触发拖拽）
    └── 否 → 视为拖拽（进入DRAGGING状态）
```

**判定规则**：

| 条件               | 结果   | 后续动作                  |
| ---------------- | ---- | --------------------- |
| 左键按下，移动距离 < 5像素  | 点击   | 触发点击反馈（如开心表情）         |
| 左键按下，移动距离 >= 5像素 | 拖拽   | 进入DRAGGING状态，跟随鼠标移动   |
| 拖拽中松开左键          | 拖拽结束 | 播放RELEASED动画，回到IDLE状态 |

### 4.3 投喂交互流程

```
用户右键 → "求投喂"
    ↓
宠物进入 ASKING_FOOD 状态
    ↓
在宠物附近生成葡萄汁图片（可拖拽）
    ↓
用户点击/拖拽葡萄汁到宠物身上
    ↓
葡萄汁图片消失，宠物进入 FEEDING 状态
    ↓
播放喂食动画
    ↓
在宠物前方生成豆腐图片（可被用户拖拽）
    ↓
豆腐图片停留5秒后自动消失或被用户拖拽走
    ↓
宠物回到 IDLE 状态
```

### 4.4 吃东西交互流程

```
用户右键 → "吃东西"
    ↓
宠物进入 EATING 状态
    ↓
播放吃猪蹄动画
    ↓
在宠物后方生成骨头图片（可被用户拖拽）
    ↓
骨头图片停留5秒后自动消失或被用户拖拽走
    ↓
宠物回到 IDLE 状态
```

### 4.5 首次启动免责声明（consent）

必须**阅读倒计时 + 滚动条拉到底**，"我已阅读并同意"按钮才会变绿可点；同意记录写入 `data/consent.json`，后续启动不再弹。

```
条款更新方式：修改 src/consent.py → CONSENT_VERSION = "1.x"（x 自增）
           → 下次启动时旧 consent.json 失效，用户必须重新同意。
```

***

## 5.技术栈规则

| 分类     | 技术                 | 版本 / 说明                                                                        |
| ------ | ------------------ | ----------------------------------------------------------------------------- |
| 编程语言   | Python             | 3.13+（主开发）；至少 3.10 才能跑 PySide6 + PyInstaller onedir                              |
| GUI框架  | PySide6            | GUI 框架，支持透明窗口、无边框、托盘、右键菜单                                                        |
| 状态管理   | FSM（有限状态机）        | `src/pet_state_machine.py` 自定义实现                                                 |
| 动画处理   | QMovie + QPixmap   | GIF 通过 `QMovie.setSpeed(fps*10)` 控制播放速度；静态 PNG 通过 `QPixmap.scaled(KeepAspectRatio, Smooth)` 等比缩放。**运行时尺寸改从 `data/settings.json` 的 `AppConfig(pet_height, always_on_top)` 读取，`PetAnimator.apply_app_config` 在启动/改设置后生效。** |
| 免责声明   | PySide6 QDialog    | `src/consent.py`：倒计时 + 滚动到底才能点继续，consent 版本号管理                            |
| 打包工具   | PyInstaller        | onedir 模式（比 onefile 启动快，好调试）                                                         |
| 安装包制作  | Inno Setup 6+      | `scripts/build_installer.iss`：现代向导、自定义安装目录、桌面快捷方式/开机自启、卸载二次确认保留数据                |
| 图像处理   | Pillow             | 素材预处理工具链（`assets-collect/frames_to_gif.py` 合成 3:4 透明 GIF、`check_image_sizes.py` 批量看 W×H） |
| 视频抽帧   | FFmpeg（子进程调用）    | `assets-collect/video_to_frames_and_gif.py`：录屏 mp4 → 按 fps/crop 抽 PNG → 合 GIF（**不做 bundle 解包**） |
| 网络请求   | requests + Selenium | B站 WBI 本地签名；抖音 Selenium 扫码登录 + yt-dlp 下载（yt-dlp 以子进程方式调用）                      |
| 数据存储   | JSON               | 显示设置 `data/settings.json`（窗口置顶/宠物高度）、`consent.json`、爬虫 Cookie 双快照（json + Netscape txt 两份）                                  |
| 外部工具   | FFmpeg / 便携版 Chrome | support/ 下分放：`support/ffmpeg.exe`、`support/Chrome/`（yt-dlp、Selenium 用，独立 Profile-Dir）          |
| 打包主入口  | `scripts/build_all.py` | 一键：exe → 绿色版 zip → 安装包 exe → 源码 zip（4 步 3 产物）                                           |

***

## 6.打包 & 发布策略（§6 重写 — v3 已落地实现）

### 6.1 资源路径处理策略（四函数分离，`src/resource_manager.py` 已实现）

| 资源类型               | 处理方式                                 | 说明                                                                    |
| ------------------ | ------------------------------------ | --------------------------------------------------------------------- |
| 只读资源（assets/ 图片、动画） | **打包进 `_internal/assets`**（PyInstaller datas） | 开发态：项目根目录；打包后：`sys._MEIPASS/assets/`                                    |
| 运行时数据（data/）      | **exe 同目录**（`{app}/data`）                | `settings.json` / `consent.json` / `cookies.*`，卸载默认保留                                           |
| 输出目录（output/）     | **exe 同目录**（`{app}/output`）               | B站/抖音爬虫下载的视频封面等，用户直接访问                                              |
| 外部工具（support/）    | **exe 同目录**（`{app}/support`）              | `ffmpeg.exe`、便携版 Chrome + Profile-Dir，体积大不进 PyInstaller datas，单独随绿色版/安装包分发                  |

四函数约定：
```
get_resource_path(p) ── 开发态: / ; 打包后: sys._MEIPASS/   （只读资产）
get_data_path(p)     ── 开发态: / ; 打包后: exe同目录/       （用户数据，可写）
get_output_path(p)   ── 开发态: / ; 打包后: exe同目录/       （输出结果，可写）
get_support_path(p)  ── 开发态: / ; 打包后: exe同目录/       （外部二进制，只读+可执行）
```

### 6.2 产物 & 打包链路（3 个脚本 + 1 个总入口 = 3 类发布产物）

```
scripts/build_all.py                  ← 一键总入口（默认产物：绿色版+安装包+源码）
 ├─ scripts/build_exe.py              ① 调用 PyInstaller + scripts/pet.spec
 │                                      ↓
 │                                   dist/pet/pet.exe
 │                                   dist/pet/_internal/  (Qt6/Python/打包后的 assets/)
 │
 ├─ scripts/build_portable.py         ② 组装绿色版 zip
 │                                      ↓
 │                                   release/DesktopPet-Portable-{version}.zip
 │                                    └─ 解压即用：启动宠物.bat + pet.exe + _internal + support/README + 空data/output
 │
 ├─ scripts/build_installer.py        ③ 调用 ISCC.exe 编译 scripts/build_installer.iss
 │                                      ↓
 │                                   release/DesktopPet-Setup-{version}.exe
 │                                    └─ Inno Setup 安装向导：可选安装路径 / 桌面快捷方式 / 开机自启，卸载二次确认保留用户数据
 │
 └─ （build_all.py 末尾）              ④ 打包仓库源码 zip（不包含 dist/build/release/.venv/support 二进制/assets-collect/output）
                                        ↓
                                     release/DesktopPet-Source-{version}.zip
```

- 命令速记：
  ```bash
  python scripts/build_all.py                                  # 全部 3 产物：绿色版 + 安装包 + 源码
  python scripts/build_all.py --version 1.0.0                  # 指定版本号（默认=git tag 或 YYYYMMDD）
  python scripts/build_all.py --only portable                  # 只出绿色版
  python scripts/build_all.py --only installer                 # 只出安装包
  python scripts/build_all.py --skip exe                       # 跳过 build_exe，复用已有 dist/pet/
  ```

### 6.3 图标规范（**两个图标文件，分离职责**）

> 项目**不做代码签名**（避免首次启动 SmartScreen 提示签名不符的警告 + 证书采购额外成本）。仅嵌入 VS_VERSIONINFO 资源，`pet.exe → 属性 → 详细信息` 能看到发布者/版本号即可。

| 用途              | 文件路径                       | 推荐尺寸                   | 当前状态    |
| --------------- | -------------------------- | ---------------------- | ------- |
| 主程序图标（pet.exe）     | `assets/icons/app.ico`      | **256×256**（ico 自动含 16/32/48/64/128/256 一套） | 待准备（缺失时用 PyInstaller 默认） |
| 安装包向导图标（setup.exe） | `assets/icons/installer.ico`| **256×256**（ico 同上）        | 待准备（缺失时 Inno Setup 用默认） |
| Inno Setup 向导左侧横幅图     | `assets/icons/WizardImage.bmp` | **164×314 px**（100% 缩放，96DPI） | 可选，缺失时向导为纯色 |
| Inno Setup 小方形图        | `assets/icons/WizardSmallImage.bmp` | **55×58 px**       | 可选，缺失时不显示 |

在 `scripts/pet.spec` 里写了自动 fallback：**图标文件不存在也不报错**，打包不会阻塞。

### 6.4 PyInstaller onedir 模式关键配置（`scripts/pet.spec`）

| 配置项 | 取值 | 说明 |
|---|---|---|
| 模式 | onedir（EXE + COLLECT 两段） | **弃用 v2 文档推荐的 `--onefile`** — onedir 启动快 3~8 秒，用户卸载升级不用重新解压整个 app 到 temp |
| datas | `(ASSETS_DIR, 'assets')` | 整个 `assets/` 目录打包进 `_MEIPASS/assets/`，素材随 exe |
| console | False（`--windowed`） | 没有终端黑窗；爬虫/协议弹窗里所有阻塞交互都走 PySide6 Dialog，不允许 `input()` |
| hiddenimports | PySide6 6 个模块 + selenium + requests | 显式声明更稳 |
| UPX | 开启，但排除所有 Qt6 dll + python3*.dll | UPX 压 Qt 会导致启动崩溃 |
| version | `VSVersionInfo` 四元组版本 | pet.exe 属性页显示「净无欲-王涵桌面电子宠物 / FileVersion / CompanyName=锐尘ruichen」，【不是】代码签名 |
| icon | `assets/icons/app.ico` if exists else None | 自动 fallback |

### 6.5 安装包（Inno Setup）关键行为

- **安装目录可选**：`DisableDirPage=no` + `DefaultDirName={autopf}\DesktopPet`，用户在向导里可改成任意路径。
- **附加任务**（用户勾选）：`desktopicon` 桌面快捷方式（默认勾）、`startupicon` 开机自启（默认不勾）。
- **开始菜单**：程序组 + 卸载快捷方式。
- **安装后启动**：`[Run]` 勾选 "立即启动"。
- **卸载二次确认**：卸载到最后弹 MsgBox 问"是否同时删除 data/output/support/Chrome 用户资料？"——默认"否"保留用户数据，选"是"才清空。
- **`uninsneveruninstall` 标签**：`data/`、`output/`、`support/` 目录即使勾了卸载也不自动删，防止误操作把爬虫下载的几十 G 视频一锅端。

### 6.6 打包后用户侧目录结构

**绿色版解压后 / 安装包安装到 `C:\Program Files\DesktopPet\`：**
```
DesktopPet/
├── 启动宠物.bat                （绿色版独有，双击代替找 pet.exe）
├── pet.exe                     主程序（2-4MB，不含 dll）
├── _internal/                  PyInstaller onedir 依赖（Qt6/Python3.13/打包的 assets/）
│   ├── assets/                 ← 只读副本，用户改 assets/ 外面那份也没用，要重新打包
│   └── ...（Qt6Core.dll、python313.dll 等）
├── assets/                     （可选保留一份副本方便用户替换，需重新打包才生效）
├── support/
│   ├── README.md               说明 ffmpeg/Chrome 怎么放进来
│   ├── ffmpeg.exe              （绿色版/安装包默认可以不带，用户按 README 放进来）
│   └── Chrome/                 （便携版 Chrome + Profile-Douyin / Profile-Bilibili，运行时产生）
├── data/                       ★ 用户数据（卸载默认保留）
│   ├── consent.json            首次同意记录（src/consent.py v1.4）
│   ├── settings.json           窗口置顶、宠物大小、代理配置等
│   ├── douyin_cookies.json     Selenium → requests 的 Cookie 快照
│   └── douyin_cookies.txt      yt-dlp --cookies Netscape 格式
└── output/                     ★ 爬虫 / 导出产物（卸载默认保留）
    ├── bilibili/*.mp4
    └── douyin/*.mp4
```

### 6.7 源码包打包（Source zip）— v3 新增

`python scripts/build_all.py` 末尾会自动生成 `release/DesktopPet-Source-{version}.zip`，
**严格排除以下目录/文件**（法务/体积敏感）：

| 排除规则 | 原因 |
|---|---|
| `dist/`、`build/`、`release/`、`.venv/` | 构建产物、虚拟环境，体积大，源码分发不需要 |
| `__pycache__/`、`*.pyc`、`.idea/`、`.vscode/`、`*.log` | IDE/运行垃圾 |
| `support/**`（除 `support/README.md`）| 外部二进制工具（ffmpeg、便携 Chrome 体积几十~几百 MB），与源代码无关 |
| **`assets-collect/`**（**整个目录排除**） | 本地私有素材提取工具链，不进入任何公开发布物（用户之前明确说明"不属于这个项目"） |
| `data/*.json`、`data/*.txt` | 用户隐私数据（consent、cookies 等） |
| `output/**` | 爬虫下载的媒体文件，版权 + 体积敏感 |
| `assets/*.gif`、`assets/*.mp3` | 试验 GIF/音效（gitignore 已排除），正式素材替换后可按需选择是否打包进源码 zip |

***

## 7.项目目录结构（v3 更新）

```
Desktop Pet/
├── main.py                        # 入口（先 check_consent_or_quit() → 再启动主窗口+爬虫 worker）
├── requirements.txt               # Python 依赖（PySide6 / pyinstaller / selenium / requests / Pillow / yt-dlp）
├── .gitignore                     # 规则已写：data/output/support 二进制/assets-collect/output+bundles-local+inventory
│
├── src/                           # 源代码（打包进 exe）
│   ├── __init__.py
│   ├── consent.py                 # 首次启动免责声明（CONSENT_VERSION=1.4，倒计时+滚到底）
│   ├── main_window.py             # 主透明窗口、右键菜单、设置对话框、代理配置、关于面板
│   ├── pet_state_machine.py       # FSM 状态机（10 个状态 + 转换表）
│   ├── pet_animator.py            # PET_HEIGHT=240 / ITEM_HEIGHT=80，等比缩放自动播放
│   ├── interaction.py             # 左键 5px 点击 vs 拖拽阈值、拖动中窗口跟随
│   ├── resource_manager.py        # get_resource_path / get_data_path / get_output_path / get_support_path
│   ├── emotion_system.py          # 情绪系统（预留）
│   └── crawler/
│       ├── gui_workers.py         # QThread Worker：Selenium 爬虫不阻塞 UI，Qt signal 通信
│       ├── bilibili.py            # B 站 WBI 签名 + Selenium 兜底
│       └── douyin.py              # 抖音：扫码登录 3 处 Cookie 持久化 + yt-dlp 下载 + 置顶过滤修复
│
├── scripts/                       # 打包脚本（v3 新增 5 个）
│   ├── build_all.py               # 一键主入口：exe → portable → installer → 源码 zip（3+1 产物）
│   ├── build_exe.py               # PyInstaller 封装：环境校验 → 调 pet.spec → dist/pet/
│   ├── pet.spec                   # PyInstaller 配置（onedir + assets datas + version info）
│   ├── build_portable.py          # 组装绿色版 zip：pet.exe + _internal + 启动.bat + support/README
│   ├── build_installer.py         # Inno Setup ISCC.exe 封装：自动探测路径 + 版本号注入
│   └── build_installer.iss        # Inno Setup 脚本：安装向导 / 任务 / 卸载二次确认 / 图标
│
├── assets/                        # 只读素材（打包进 exe，PyInstaller datas 引用）
│   ├── README.md                  # 素材替换说明
│   ├── 试.gif / 试.png / 试_物品东西.png / 试.mp3   # 试验占位素材（.gitignore 已锁 gif/mp3 不入库）
│   └── icons/                     # 图标文件（v3 规范，缺了也能打包）
│       ├── app.ico
│       ├── installer.ico
│       ├── WizardImage.bmp
│       └── WizardSmallImage.bmp
│
├── support/                       # 外部工具（运行时目录，.gitignore 锁死二进制只留 README）
│   └── README.md                  # ffmpeg/便携版 Chrome 放置说明
│
├── data/                          # 运行时用户数据（.gitignore *.json/*.txt）
│   └── .gitkeep
│
├── output/                        # 输出目录（爬虫/导出物，.gitignore 全锁）
│   └── .gitkeep
│
├── docs/                          # 设计文档
│   ├── Desktop pet frame.md       # v1 初始
│   ├── Desktop pet frame v2.md    # v2 初版功能框架
│   └── Desktop pet frame v3.md    # ★ v3 当前：打包策略/目录/协议落地版
│
├── release/                       # 打包输出（.gitignore 锁死，不入库）
│   ├── DesktopPet-Portable-{version}.zip
│   ├── DesktopPet-Setup-{version}.exe
│   └── DesktopPet-Source-{version}.zip
│
├── build/  dist/                  # PyInstaller 构建临时目录（.gitignore 锁死）
│
└── assets-collect/                # ★ 本地私有素材生产工具链 — 不随项目公开 ★
    ├── README.md                  # 使用说明 + 录屏 → 达芬奇裁抠 → 抽帧/GIF 全流程
    ├── requirements.txt           # 本工具链依赖（Pillow；FFmpeg 走子进程/系统 PATH）
    ├── video_to_frames_and_gif.py # 录屏 mp4 → 抽 PNG 帧（支持 crop/ss/to/fps/size）→ 可选直接合 GIF
    ├── frames_to_gif.py           # 达芬奇导出的 PNG 序列 → 合成 3:4 统一尺寸 GIF（带透明，--size）
    ├── check_image_sizes.py       # 扫文件夹所有 PNG/GIF 输出 W×H，不用装看图软件
    └── output/                    # 抽帧/GIF 产物（.gitignore 锁死，不进仓库）
```

> ⚠ **特别声明**：`assets-collect/` 仅用于**个人学习+本地素材生产**（录屏→抽帧→合 GIF，不走逆向/解包路线）。**绝不**：
> 1. 随 `release/` 三个产物打包；
> 2. 进入公开仓库（发布前可在 `.gitignore` 把 `# assets-collect/` 行的 `#` 取消注释整体排除）；
> 3. 用于商业用途或二次分发。
>
> 🛑 原 v1 方案（UnityPy/Frida 解影游加密 bundle）已废弃：
> - 8727/8735 个 bundle 为自定义 AES 加密，IL2CPP 后端 `SetAssetBundleDecryptKey` 无符号且 key 未落在可扫描内存区；
> - 对应的 `scan_bundles.py / extract_assets.py / bundle_decrypt.py / frida_hook_key.py`、`bundles-local/`、`inventory.json` **用户已手动删除**，文档不再维护。
> - 之后所有素材统一走「Win+Alt+R 录屏 → 达芬奇裁剪抠透明 → frames_to_gif.py 合 3:4 GIF」的合法合理使用链路。

***

## 8.开发计划（v3 更新：实际实现进展）

### 8.1 第一阶段：基础功能 ✅ 已全部实现

| 序号 | 任务    | 状态      |
| -- | ----- | ------- |
| 1  | 项目初始化 | ✅ 已完成   |
| 2  | 透明窗口  | ✅ 已完成   |
| 3  | 状态机基础 | ✅ 已完成（10 状态） |
| 4  | 待机/走路/拖拽/松开 | ✅ 已完成 |
| 5  | 右键菜单  | ✅ 已完成（含拓展功能→抖音/B站/ihan/设置/退出） |
| 6  | 首次启动免责声明 | ✅ 已完成（consent v1.4：倒计时 + 滚到底） |

### 8.2 第二阶段：高级功能 ✅ 已全部实现

| 序号 | 任务    | 状态      |
| -- | ----- | ------- |
| 7  | 吃东西功能 | ✅ 已完成   |
| 8  | 求投喂功能 | ✅ 已完成   |
| 9  | 喂食功能  | ✅ 已完成   |
| 10 | 睡觉/玩耍/生气状态 | ✅ 已完成（ASSET_MAP 映射已写，换正式素材即生效） |
| 11 | 代理设置  | ✅ 已完成（main_window 设置对话框里 HTTP/SOCKS5h/鉴权） |

### 8.3 第三阶段：拓展功能 ✅ 已集成

| 序号 | 任务      | 状态      |
| -- | ------- | ------- |
| 12 | B站爬虫集成 | ✅ 已集成   |
| 13 | 抖音爬虫   | ✅ 已集成（登录循环修复、置顶视频过滤修复） |
| 14 | ihan 粉丝站彩蛋 | ✅ 已集成 |
| 15 | 便携 Chrome + Cookie 双快照 | ✅ 已实现（3 处登录数据：Profile-Dir + json + txt，菜单一键清除） |

### 8.4 第四阶段：打包封装 ✅ 已落地

| 序号 | 任务   | 状态      |
| -- | ---- | ------- |
| 16 | PyInstaller onedir 规范打包（pet.spec） | ✅ 已完成：datas/assets、version info、UPX 排除 Qt dll |
| 17 | 绿色版 zip 构建脚本（build_portable.py） | ✅ 已完成 |
| 18 | Inno Setup 安装包（build_installer.iss + py） | ✅ 已完成：自定义目录/快捷方式/开机自启/卸载二次确认 |
| 19 | 源码 zip 打包（排除 support/.venv/assets-collect）| ✅ 已完成（build_all.py 末尾自动生成） |
| 20 | 一键总入口 build_all.py --version --skip --only | ✅ 已完成 |

### 8.5 第五阶段：素材 & 正式发布（进行中）

| 序号 | 任务     | 状态      |
| -- | ------ | ------- |
| 21 | 人物动作素材制作（10 个状态 GIF + 1 拖拽静态） | 🔧 进行中（达芬奇裁紧 → frames_to_gif.py，3:4 基准） |
| 22 | 物品素材（骨头/葡萄汁/豆腐单独 PNG）          | 🔧 进行中 |
| 23 | 应用程序图标（app.ico + installer.ico）       | 待准备（尺寸规范见 §6.3） |
| 24 | 音效替换（试.mp3 → 正式动作音）               | 待准备 |
| 25 | 替换 ASSET_MAP 映射（`src/pet_animator.py:34`）| 素材到位后改一行 |
| 26 | 正式版本号打 tag，跑 `build_all.py` 产出 release/ 3 个产物 | 最后一步 |

***

## 9.注意事项

### 9.1 图片资源注意事项

| 事项   | 说明                                                                                              |
| ---- | ----------------------------------------------------------------------------------------------- |
| 图片格式 | 推荐 **PNG**（支持透明背景），动画用 **GIF**（Pillow 2-pass 调色板 dither=bayer:bayer_scale=3 画质好） |
| 人物比例 | **宽:高 = 3:4 竖图**（基准：306×372 试验图），典型原始制作 360×480 或 480×640；程序统一缩到显示 180×240                          |
| 物品尺寸 | 原始导出 120~160px 高；程序按 `ITEM_HEIGHT=80` 缩                                                          |
| 图标尺寸 | **256×256 方形 PNG**（app.ico/installer.ico），.ico 文件里最好自带 16/32/48/64/128/256 六档尺寸                                  |
| 图片命名 | 按状态英文小写：`idle.gif` `walking.gif` `dragging.png` `bone.png` `grape_juice.png` |
| 引用保存 | PySide6 代码里所有 QMovie / QPixmap 对象必须 `self._movie` / `self._pixmap` 保留引用，避免 GC 导致"显示空白"                      |
| 尺寸预检 | `python assets-collect/check_image_sizes.py --folder <路径>` 一键看 W×H，不用装看图软件                                             |

### 9.2 打包注意事项

| 事项             | 说明                                                                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 产物              | **跑一个命令就全出**：`python scripts/build_all.py`；需要单独跑时 `--only portable` / `--only installer` / `--skip exe`                                 |
| 模式              | 用 **onedir（EXE + COLLECT）**，不要回 v2 的 `--onefile` — onedir 启动快、好排查、data/output/support 路径都在 exe 同目录，符合用户预期。                           |
| 控制台             | `console=False`，爬虫和协议交互**禁止用 `input()` / `print()`** — 全部走 QDialog（抖音扫码用便携 Chrome，日志走 Qt signal 显示在 GUI 对话框里）。 |
| 图标缺失不阻塞打包        | `scripts/pet.spec` 和 `build_installer.iss` 都做了 `if FileExists(...)` fallback，没准备图标也能打包（只是默认图标）。                                         |
| 首次启动免责声明         | 打包后**一定有效**（`consent.py` 的 `get_data_path` 已按打包态定位到 `{app}/data/consent.json`），条款更新 bump `CONSENT_VERSION` 就行。                |
| support/ 外部工具分发策略 | **不进 PyInstaller datas**；绿色版 zip 里只放 `support/README.md`，ffmpeg / 便携 Chrome 按 README 由用户自行放到安装目录下（因为体积 + 版权分发问题）。            |
| 升级不覆盖用户数据        | Inno Setup 的 `[Dirs] uninsneveruninstall` + 卸载 MsgBox 默认保留 data/output/support/Chrome 3 处，防止覆盖用户已扫码登录态 / 已下载视频。              |
| assets-collect/ 不发布    | 整个目录：① 不进绿色版 zip ② 不进安装包 ③ 不进 Source zip（`shutil.make_archive(base_dir='src ...', exclude_dirs=['assets-collect', ...])`）；发布前可在 .gitignore 取消 `# assets-collect/` 行注释整目录排除。 |

### 9.3 爬虫注意事项（v2 内容保留，保持一致）

| 事项                  | 说明                                                                                                                                                                                                                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 反爬机制                | B站 / 抖音都有严格的 UA / 自动化指纹检测，Selenium 启动时务必：`--disable-blink-features=AutomationControlled` + `excludeSwitches: ['enable-automation']` + CDP 注入隐藏 `navigator.webdriver`；请求间隔加随机抖动。                                                                                                                   |
| 抖音登录态与 Cookie 存放  | **共 3 处，均允许用户一键删除**（GUI 菜单：拓展功能 → 抖音 → 清除登录数据（退出登录））：<br>① `support/Chrome/Profile-Douyin/` — 便携 Chrome 的独立用户资料目录（**最完整**，含 Cookie / localStorage / 缓存 / 登录态）<br>② `data/douyin_cookies.json` — Selenium / requests 注入用的快照<br>③ `data/douyin_cookies.txt` — yt-dlp 下载时 `--cookies` 需要的 Netscape 格式。<br>**首次登录**：菜单「登录/重新登录（扫码）」→ 弹便携版 Chrome → 用抖音 App 扫码 → 回 GUI 弹窗确认「登录完成」。不需要、也绝对不应该在代码里写账号密码。 |
| 抖音下载                | 不自己手写 a_bogus/X-Bogus 签名（维护成本极高）。**统一交给 yt-dlp + cookies.txt 下载**，yt-dlp 官方长期跟进抖音签名 / 反爬维护。                                                                                                                                                                                                          |
| B站登录                | B 站空间页目前大部分内容不需要登录；WBI 签名算法在本地做。如果要抓隐私空间 / 充电内容，可复用抖音的同一套「便携 Chrome + 独立 Profile-Dir + Cookie 双快照」方案（Profile 可以不共用，建 `support/Chrome/Profile-Bilibili`）。                                                                                                                      |
| 数据存储                | 爬取得到的视频、封面等文件按平台分目录：`output/bilibili/`、`output/douyin/`；爬虫日志和 Cookie 存在 `data/` 下。                                                                                                                                                                            |
| 用户隐私                | 登录态文件（cookie.json / txt / Chrome Profile 目录）严禁提交到 Git / 打包公开共享。`.gitignore` 中 `data/*.json`、`data/*.txt`、`support/Chrome/Profile-*` 已建议忽略。                                                                                                                                                                    |
| GUI 线程隔离            | Selenium 爬虫一律跑在 QThread Worker（`src/crawler/gui_workers.py`），不阻塞主 UI；日志 / 成功 / 失败 / 需用户交互 全部走 Qt 信号，避免在 PyInstaller --windowed 打包环境下因 `input()` / 终端导致程序崩溃。                                                                                                                               |

### 9.4 菜单结构（右键，v3 最终：与代码一致）

```
吃东西
求投喂
喂食
───
拓展功能 ▶
├─ 爬取B站最新视频
├── 抖音 ▶
│   ├─ 爬取抖音最新视频             (未登录会先弹"请先登录"的友好提示)
│   ├─ 登录/重新登录（扫码）         (一次扫码，后续 Profile 自动复用)
│   └─ 清除登录数据（退出登录）       (删除 3 处登录数据，带二次确认 + 路径说明弹窗)
├─ 代理设置…                        (HTTP / SOCKS5h + 可选鉴权；仅爬虫使用)
├─ 清除隐私数据…                     (可勾选：代理配置 / 抖音登录 / data/settings.json；带二次确认 + 汇总弹窗)
├─ 打开 data 目录
└─ 打开 output 目录
设置 ▶
├─ ☑ 窗口置顶                        (默认开，勾选取消后任何全屏应用会盖住宠物；写入 data/settings.json)
├─ 调整宠物大小…                     (高度 120~480 px；小/中/大 3 档预设；物品图自动按 1/3 高度联动缩放)
└─ 恢复默认设置                       (一键重置：置顶开 + 高度 240 px；二次确认不碰爬虫数据)
───
关于此项目 ▶
├─ GitHub
├─ Gitee
└─ ihan 粉丝站 ✨
───
退出
```

***

## 10.扩展预留区域

### 10.1 未来功能设想

- [ ] 宠物成长系统：宠物随时间成长，外观变化
- [ ] 小游戏：与宠物互动的迷你游戏
- [ ] 语音交互：支持语音命令和语音反馈
- [ ] 多宠物支持：同时运行多个宠物
- [ ] 宠物换装：更换宠物外观皮肤
- [ ] 社交功能：分享宠物截图到社交平台
- [ ] 天气同步：根据天气变化改变宠物行为
- [ ] 节日主题：在特定节日显示节日装饰

### 10.2 技术扩展方向

- [ ] 代码签名（EV 证书，消除 SmartScreen 警告）——当前故意不用（见 §6.3 说明）
- [ ] 自动更新机制（GitHub Release API 拉最新 Source/Setup zip）
- [ ] 插件热更新机制
- [ ] 国际化（中文/英文双语）
- [ ] 跨平台打包（Linux AppImage / macOS DMG，目前脚本都是 Windows 专用）
