# LaTeX 中文论文模板

## 使用方法

1. 复制整个模板文件夹作为新项目。
2. 编辑现有 `.tex` 文件；如果重命名，请保留 `.tex` 扩展名。
3. 在项目文件夹中运行：

   ```powershell
   .\build.ps1
   ```

   编译后的 PDF、日志、目录和其他辅助文件都会放在 `build/`，源文件目录保持整洁。

如果项目根目录有多个 `.tex` 文件，请指定主文件：

```powershell
.\build.ps1 -MainFile report.tex
```

模板也已配置 VS Code 的 LaTeX Workshop。打开复制后的文件夹，在 `.tex` 文件中触发构建，输出同样进入 `build/`。

## 编译环境

需要安装 TeX Live（包含 XeLaTeX）及模板使用的中文字体。模板默认使用 `ctexart`、宋体、黑体、仿宋和 Times New Roman。
