# 锅巴小公主 — Windows 桌宠

一款基于 PySide6 的 Windows 桌面宠物，支持多角色、便签、番茄钟、快速启动菜单等功能。

## 功能特性

- 🎭 **多角色切换**：支持娇阿依、何小猿、锅巴、维维、银狼等角色，右键菜单一键切换
- 📝 **便签系统**：彩色便签，支持增删改查
- ⏱️ **番茄钟**：专注倒计时，任务+时间头顶显示
- 🚀 **快速启动**：可自定义的快速启动菜单
- 🔒 **锁定模式**：禁止自动乱跑，但保留甩出和边界跳跃
- 🖱️ **交互**：拖拽甩出、悬停打招呼、撞边张望

## 一键运行（无需安装 Python）

下载后直接双击运行：

```
GuobaPrincess.exe          # 直接运行桌宠
run-deskpet.bat            # 同上（批处理入口）
```

首次运行会自动切帧缓存到 `%APPDATA%\GuobaPrincess\`，后续启动更快。

---

## 开发说明

### 项目结构

```
├── src/
│   ├── deskpet.py      # 主程序（入口）
│   ├── animator.py     # 动画状态机
│   ├── atlas.py        # 精灵图切帧工具
│   └── config.py       # 配置持久化
├── assets/characters/  # 角色素材
│   ├── jiaoyi/         # 源图 + 预切帧
│   ├── hexiaoyuan/     # 预切帧
│   ├── guoba/          # 预切帧
│   ├── weiwei/         # 预切帧
│   └── yinglang/       # 源图（运行时自动切帧）
├── gxy-deskpet.spec    # 桌宠 PyInstaller 打包配置
├── Setup-GuobaPrincess.spec  # 安装包打包配置
├── GuobaPrincess.exe   # 已打包的单文件桌宠（可直接运行）
├── gxy.ico / gxy.png   # 图标
├── requirements.txt
└── README.md
```

### 环境要求

- Python 3.10+
- Windows 10/11

### 从源码运行

```bash
pip install -r requirements.txt
python src/deskpet.py
```

### 打包命令

```bash
# 打包桌宠（单文件）
python -m PyInstaller -y gxy-deskpet.spec

# 打包安装包（单文件）
python -m PyInstaller -y -F --add-data "dist\GuobaPrincess.exe;." --name "Setup-GuobaPrincess" --windowed --icon "gxy.ico" src/setup.py
```

---

## 添加新角色

1. 在 `assets/characters/` 下新建文件夹，如 `mynewchar/`
2. 放入 `spritesheet.webp`（1536×1872，8×9 网格）
3. 在 `src/deskpet.py` 的切换角色菜单里添加：
   ```python
   ("mynewchar", "我的角色")
   ```
4. 重新运行即可，程序会自动切帧

## 角色素材规范

精灵图必须是 **1536×1872** 像素，按 **8 行 × 9 列** 排列：

| 行 | 动作 | 帧数 |
|---|---|---|
| 0 | idle | 6 |
| 1 | running-right | 8 |
| 2 | running-left | 8 |
| 3 | waving | 4 |
| 4 | jumping | 5 |
| 5 | failed | 8 |
| 6 | waiting | 6 |
| 7 | running | 6 |
| 8 | review | 6 |

## 注意事项

- 窗口无边框、透明背景、置顶显示
- 配置和切帧缓存保存在 `%APPDATA%\GuobaPrincess\`
- 单文件模式（`--onefile`）运行时会解压到临时目录
