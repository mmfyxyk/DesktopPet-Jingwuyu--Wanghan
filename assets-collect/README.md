# 本目录 /assets-collect/ 说明（**不随桌宠发布，仅供本地个人素材生产使用**）

本目录是**本地私有工具链**，用于把「影游剧情录屏 → 达芬奇裁紧抠透明 → 批量 PNG 序列 合成统一 3:4 GIF / 预检尺寸」的枯燥重复动作脚本化，最终产物复制到 `assets/` 下作为桌宠正式素材。

> ⚠️ **不做逆向、不做解包、不拿 bundle 原始资源。** 原方案（UnityPy / Frida 抓 AES key 解影游 `.bundle`）已于 2026-08 废弃：
> 游戏 8727/8735 个 `.bundle` 使用自定义 AES+IL2CPP 且 key 不落地内存，逆向获取成本和法律风险都远超收益，
> 之后所有素材统一走「**自己电脑上合法拥有的游戏 + 录屏 + 达芬奇裁剪抠透明 + 合 GIF**」的合理使用链路。

> 📜 **法律与合规声明（请务必遵守）**：
>
> 1. 本目录内的脚本和生成的 GIF/PNG 仅供**个人学习、研究、非商业粉丝向二次创作**使用；
> 2. 你必须已经合法拥有（Steam 购买）目标游戏；
> 3. 不得把未加工或极少加工的整段视频、完整人物立绘上传到公开仓库/分发平台；
> 4. `output/` 及你本地录屏的 mp4 素材**一律不得**进 git；
> 5. 请遵守目标游戏 EULA、Steam 用户协议、版权法中关于个人合理使用范围的条款。

---

## 目录结构

```
assets-collect/
├── README.md                  ← 本文件
├── requirements.txt           ← 依赖：仅 Pillow（FFmpeg 走子进程/系统 PATH）
├── video_to_frames_and_gif.py ← 录好的 mp4 → 按 fps/crop/size 抽 PNG 帧 + 可选直接合 GIF
├── frames_to_gif.py           ← 达芬奇裁紧抠完的 PNG 序列 → 合成 3:4 统一尺寸的 GIF（支持透明）
├── check_image_sizes.py       ← 扫文件夹所有 PNG/GIF 输出 W×H，不用装看图软件
└── output/                    ← 抽帧 / 合成 GIF 产物（.gitignore 已锁，不进仓库）
```

外部依赖（**需要你电脑上已装好，不用 pip**）：

| 工具 | 用途 | 哪里拿 |
|---|---|---|
| **ffmpeg.exe** | `video_to_frames_and_gif.py` 抽帧用（零损耗解码） | [ffmpeg.org 下载页](https://www.ffmpeg.org/download.html) → Windows essentials build → 解压后把 bin 路径加 PATH，或者直接放 `support/ffmpeg.exe` |
| **达芬奇 / 免费版 DaVinci Resolve** | 裁剪 + 抠透明背景 + 导出 PNG 序列 | DaVinci 官网免费版，功能够用 |
| **Windows Xbox Game Bar**（Win+Alt+R）或 OBS 游戏捕获 | 录制剧情片段 | Windows 自带 / OBS 官网 |

---

## 用法

### 1. 安装 Python 依赖

```bash
pip install -r assets-collect/requirements.txt
```

> 就一个 **Pillow**，专门负责 GIF 透明帧合图（`disposal=2` 去残影）+ 读图片尺寸。  
> 以前的 UnityPy / pycryptodome / frida / psutil / tqdm 都已经删掉不再需要。

### 2. 素材流水线（推荐：达芬奇 → PNG 序列 → `frames_to_gif.py`）

#### 2.1 录屏 → 裁剪抠图 → 导出 PNG 序列

1. **Win+Alt+R**（或 OBS 游戏捕获无损）录某段剧情，5~15 秒一个动作；
2. 扔进达芬奇 → **裁紧人物（留 5% 顶 / 10% 底空白即可）** → Fusion 页面抠 Chroma/Luma 键 → **导出为 PNG 序列**（480 高左右，不用再缩放）。
3. 所有 PNG 帧放到一个空文件夹，比如 `D:\素材\王涵_idle_frames\`。

#### 2.2 合成 3:4 统一尺寸 GIF

```powershell
# 推荐：按达芬奇导出的 PNG 序列合 3:4 透明 GIF（桌宠标准画布）
python assets-collect/frames_to_gif.py `
    --folder "D:/素材/王涵_idle_frames" `
    --out    "assets-collect/output/王涵_idle.gif" `
    --fps 8 `
    --size 360x480 `
    --transparent
```

常用开关：

| 参数 | 作用 |
|---|---|
| `--fps 8` | GIF 帧率：idle 用 6~8、走路用 10~12、吃东西可以 15+ |
| `--size 360x480` | **强制 3:4 统一画布**，人物等比缩放居中，空处透明（--transparent）或白底（不加） |
| `--transparent` | 保留达芬奇抠的透明像素，桌宠显示就不会有白边（**推荐**）|
| `--loop 0` | 永远循环（默认 0 无限），如果只是挥手动作一次性可以 `--loop 1` + 代码里接 `animation_finished` 信号 |
| `--palette 256` | 颜色数，256 默认就够；背景颜色多的素材可以改 `--dither` 去掉色带 |

### 3. 快速流水线（不用达芬奇，mp4 直接抽帧 + 合 GIF）

赶时间 / 不抠透明、先快速看效果时：

```powershell
python assets-collect/video_to_frames_and_gif.py `
    --video "C:/Users/ZhuKL/Videos/Captures/xxx.mp4" `
    --crop 540:100:840:880 `    # x:y:w:h 把对话条和两边空墙裁掉
    --frames-fps 8 `              # 每秒抽 8 帧
    --gif --gif-fps 8 --gif-size 240x320
```

结果：
- `assets-collect/output/frames/xxx_00001.png` 起的 PNG 帧（你挑好的后续还能再用达芬奇抠）
- `assets-collect/output/frames/xxx.gif`（240×320，3:4）

### 4. 尺寸预检（做完一批素材后核对）

```powershell
# 扫某个文件夹
python assets-collect/check_image_sizes.py --folder "D:/素材/王涵_idle_frames"

# 不写 --folder 默认扫整个工作目录（assets/ + assets-collect/output/ + 素材/ 试一下看哪里散了素材）
python assets-collect/check_image_sizes.py
```

输出大概是：
```
试.gif                                GIF    1920×1080   19 帧   ⚠ 16:9 横（建议裁成 3:4）
试.png                                PNG      306×372   ✅ 3:4 标准
试_物品东西.png                        PNG      138×110   ✅ 物品图
```

**合格的人物素材 = W:H 接近 3:4**（比如 300×400 / 360×480 / 240×320 … 上下浮动 10% 都 OK）。程序运行时会按高度自动缩到 `PET_HEIGHT`（默认 240 px，菜单「设置 → 调整宠物大小」可改），所以不用卡得刚刚好。

### 5. 复制到桌宠素材目录

挑选好的 GIF / PNG 重命名成 `src/pet_animator.py` 中 `ASSET_MAP` 对应键：

```bash
# 拷贝覆盖占位素材（试.gif / 试.png 等）
copy "王涵_idle.gif"  "assets/试.gif"
copy "拖拽.png"       "assets/试.png"
copy "物品.png"       "assets/试_物品东西.png"
```

或者直接改 `ASSET_MAP`，把文件名换成你自己的（推荐）。

---

## 常见问题

### Q1：合出来的 GIF 有残影 / 透明边不对？

加 `--transparent`（已经是默认推荐），Pillow 会强制写 `disposal=2`（每帧先清空再画）。如果还不行，**达芬奇导出 PNG 前把画布背景切"透明 checkerboard 模式"再导一次**，确认 PNG 本身就带 alpha 通道。

### Q2：抽帧时 ffmpeg 报错 "找不到"？

两种方案选一个：
1. 直接下载 `ffmpeg.exe`，放到项目根目录 `support/ffmpeg.exe` 下；
2. 把 ffmpeg 的 `bin/` 加进系统 PATH（命令行 `where ffmpeg` 能看到就行）。

### Q3：GIF 太大，几 MB 起步？

优先降帧率：`--fps 6` → 比 12fps 省一半体积。其次降尺寸 `--size 240x320`。再不行减少帧数（`--ss` / `--to` 切更短的动作段落）。

### Q4：素材目录里人物 GIF 尺寸各不相同，切换动作时窗口跳来跳去？

**一定要**对同一人物所有动作 GIF 都跑一遍 `frames_to_gif.py --size 360x480`（或统一 `240x320`）。统一画布比例后，桌宠主程序 `PET_HEIGHT=240` 缩完大小完全一致，不会再跳。

---

## 附录：建议的素材制作 & 命名规范

| 状态 | 建议 FPS | 建议时长 / 帧数 | 对应 `ASSET_MAP` 键值 |
|---|---|---|---|
| IDLE 待机呼吸 | 6~8 | 1~2s 循环 | 试.gif（或 idle.gif，后续改映射表） |
| WALKING 走路 | 10~12 | 1~1.5s 循环 | 试.gif / walking.gif |
| DRAGGING 被拎起 | 静态 PNG，1 张 | — | 试.png / dragging.png |
| EATING 吃猪蹄 | 15~20 | 1.5~2s 循环 | eating.gif |
| ASKING_FOOD 求投喂 | 8~10 | 2~3s 循环 | asking.gif |
| SLEEPING 睡觉 | 4~5 | 2~3s 慢呼吸 | sleeping.gif |
| 物品：骨头 / 葡萄汁 / 豆腐 | 静态 PNG | 建议 120×90 左右，比例随意 | 试_物品东西.png（目前共用，后续可拆 3 张独立）|
