# Gamma 分支合并到 Main 分支的分析报告

## 概述

本报告分析了将 `gamma` 分支合并到 `main` 分支的可行性，以及对现有用户习惯的影响。

## 1. 合并可行性分析

### 技术层面

| 项目 | 状态 |
|------|------|
| 分支历史关系 | ❌ 无共同祖先 (unrelated histories) |
| 自动合并 | ❌ 存在冲突 |
| 冲突文件数量 | 4 个文件 |

**冲突文件列表：**
1. `README.md` - 文档内容完全不同
2. `main.py` - CLI接口和运行逻辑重大变更
3. `src/report/generator.py` - 报告生成逻辑变更
4. `src/utils/progress.py` - 进度显示逻辑变更

### 结论

**可以合并，但需要手动解决冲突**。由于两个分支具有不相关的历史记录，合并时需要使用 `--allow-unrelated-histories` 选项，并手动解决4个文件的冲突。

---

## 2. 对用户习惯的影响分析

### 2.1 CLI 接口变化 (⚠️ 重大变更)

#### Main 分支 (当前用法)
```bash
# 命令行参数驱动
python main.py --bib paper.bib --tex paper.tex --enable-all
python main.py --bib paper.bib --tex paper.tex --check-metadata
python main.py --bib paper.bib --tex paper.tex --check-relevance --llm deepseek
```

#### Gamma 分支 (新用法)
```bash
# 配置文件驱动
python main.py                      # 自动使用 bibguard.yaml
python main.py --config my.yaml     # 指定配置文件
python main.py --init               # 创建默认配置文件
python main.py --list-templates     # 列出可用模板
```

### 2.2 影响评估

| 变更项 | 影响程度 | 说明 |
|--------|----------|------|
| 命令行参数 | 🔴 **高** | 所有 `--bib`, `--tex`, `--check-*` 等参数被移除 |
| 配置方式 | 🔴 **高** | 从命令行参数转变为 YAML 配置文件 |
| 输出目录 | 🟡 **中** | 输出改为 `bibguard_output/` 目录 |
| 输出文件 | 🟡 **中** | 新增多种报告格式 |
| 新功能 | 🟢 **低** | 新增模板系统、会议特定检查等 |

### 2.3 用户迁移所需工作

1. **创建配置文件**：用户需要运行 `python main.py --init` 创建 `bibguard.yaml`
2. **修改配置**：将原命令行参数转换为 YAML 配置
3. **更新脚本**：任何自动化脚本需要重写

**原命令迁移示例：**

```bash
# 旧命令 (main 分支)
python main.py --bib paper.bib --tex paper.tex --check-metadata --check-usage

# 新方式 (gamma 分支)
# 1. 编辑 bibguard.yaml:
#    files:
#      bib: "paper.bib"
#      tex: "paper.tex"
#    bibliography:
#      check_metadata: true
#      check_usage: true
# 2. 运行:
python main.py
```

---

## 3. Gamma 分支新增功能

### 新增目录和文件

| 目录/文件 | 说明 |
|-----------|------|
| `src/checkers/` | 12个新检查器 |
| `src/config/` | 配置管理系统 |
| `src/templates/` | 会议模板系统 |
| `src/ui/` | 用户界面工具 |
| `src/report/line_report.py` | 行级报告生成 |
| `bibguard.yaml` | 默认配置文件 |

### 新增检查器

- `acronym_checker.py` - 首字母缩略词检查
- `ai_artifacts_checker.py` - AI生成痕迹检查
- `anonymization_checker.py` - 匿名化合规检查
- `caption_checker.py` - 标题位置检查
- `citation_quality_checker.py` - 引用质量检查
- `consistency_checker.py` - 一致性检查
- `equation_checker.py` - 公式检查
- `formatting_checker.py` - 格式检查
- `number_checker.py` - 数字格式检查
- `reference_checker.py` - 交叉引用检查
- `sentence_checker.py` - 句子质量检查

---

## 4. 建议

### 如果决定合并：

1. **发布版本说明**：清晰记录 CLI 接口的变更
2. **提供迁移指南**：帮助用户从命令行参数迁移到配置文件
3. **考虑过渡期**：可以考虑暂时保留旧的命令行参数作为兼容选项

### 如果不合并：

1. 保持 main 分支的简洁命令行接口
2. 将 gamma 作为独立的"高级版"分支维护
3. 在 README 中说明两个分支的区别和适用场景

---

## 5. 总结

| 问题 | 回答 |
|------|------|
| gamma 是否可以合并到 main？ | ✅ 技术上可行，但需要手动解决冲突 |
| 会对用户习惯有影响吗？ | ⚠️ **是的，有重大影响** |
| 影响程度 | 🔴 **高** - CLI 接口完全改变，从命令行参数驱动变为配置文件驱动 |
| 建议 | 如要合并，需提供完善的迁移文档和用户指南 |
