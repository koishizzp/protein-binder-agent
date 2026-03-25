# Protein Binder Design Agent Framework

本项目将 BindCraft、Proteina-Complexa 与 MDAnalysis 封装为可编排的多工具 Agent 框架。

## 快速开始

```bash
cd protein_agent
pip install -r requirements.txt
python main.py --help
```

## 目录结构

- `agent/`: LLM Agent 主循环、提示词、记忆与规划
- `tools/`: 三大核心工具 + 文件/结构辅助工具
- `pipeline/`: 独立可运行的编排流水线
- `config/`: agent、工具、工作流配置
- `data/`: 靶点、设计输出、分析结果、排名结果
- `tests/`: 基础单元测试

## 示例

```bash
python main.py chat "帮我为 PDL1 设计 binder"
python main.py pipeline data/targets/PDL1_5IUS.pdb --run-name demo
```
