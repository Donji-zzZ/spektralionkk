# spektralionkk

[English](README.md) | **简体中文**

适用于 Windows 的光谱胶片与印放模拟：基于 Andrea Volpato 的
[spektrafilm](https://github.com/andreavolpato/spektrafilm) 引擎打造的暗房风格修图软件。

界面支持简体中文和英文。本软件是遵循 [GNU GPL v3](LICENSE) 的自由软件。

## 下载

**[下载 spektralionkk 1.4.0 Windows 安装程序](https://github.com/Donji-zzZ/spektralionkk/releases/download/v1.4.0/spektralionkk-1.4.0-setup.exe)**（124 MB）

所有版本都在 [Releases 页面](https://github.com/Donji-zzZ/spektralionkk/releases)，该页面也提供源代码压缩包。

安装程序没有代码签名，Windows SmartScreen 可能会弹出警告：点击“更多信息”，再点击“仍要运行”。

1.4.0 版是在项目改名之前构建的，因此安装后仍会显示旧名称 sprktralionkk。

## 相比 spektrafilm 新增的内容

- **重新设计的界面：** 采用 Lightroom 风格的布局，包含导航器、风格、历史记录、胶片栏、直方图和修改面板。
- **更快的滤镜预览：** 拖动滑块时通过查找表实时更新画面，不需要独立显卡。松开滑块后再渲染全质量的颗粒、
  光晕和锐化。
- **导入你自己的照片：** 打开文件或文件夹，或直接把文件拖进来，支持 RAW、JPEG、TIFF、PNG 和 EXR。
- **自动曝光补偿：** 默认开启，可选择测光模式，也可以用滑块手动调整曝光。
- **RAW 编辑：** 支持压缩 RAW，包括索尼、佳能（CR3 和 C-RAW）、富士、尼康、松下和 DNG。少数最新的编码
  （尼康高效率 RAW、JPEG XL DNG）暂时无法解码，这时软件会改为编辑相机内嵌的全尺寸 JPEG，并给出提示。
- **压缩导出：** 把修好的 RAW 照片保存为 JPEG（质量 50–100）、16 位 TIFF 或 PNG，色彩空间可选 sRGB、
  Display P3、Adobe RGB、ProPhoto 或 Rec.2020。RAW 文件会导出为这些格式，而不是重新写成 RAW。
- **预设与 LUT：** 可导入 Lightroom / Camera Raw 预设（`.xmp`、`.lrtemplate`）和 `.cube` LUT。
- **胶片边框与日期后背：** 提供胶片条、片号和日期，画幅从半格到 4×5。

完整功能和快捷键请看[使用说明](docs/USER_GUIDE.zh-CN.txt)。

## 从源代码运行

需要 Windows 和 Python 3.13（spektrafilm 支持的版本）。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spektralionkk.app
```

在一台电脑上首次启动时会编译处理内核，大约需要 30 秒。

## 致谢与许可

- 代码：GPL-3.0，见 [LICENSE](LICENSE)。
- 胶片模拟引擎以及彩色胶片 / 相纸数据：Andrea Volpato 的 spektrafilm，代码为 GPL-3.0，数据为 CC BY-SA 4.0，
  见 [SPEKTRAFILM_LICENSE.txt](SPEKTRAFILM_LICENSE.txt)。
- 界面字体：Rasmus Andersson 的 Inter，SIL Open Font License 1.1。
- 所有内置数据（包括黑白胶片数据）的完整致谢，见[英文使用说明](docs/USER_GUIDE.txt)和
  [`spektralionkk/data/`](spektralionkk/data/)。

胶片、相机、软件和品牌名称均为其所有者的商标，仅用于说明数据、文件格式或灵感来源。spektralionkk 与上述项目或
公司均无关联。
