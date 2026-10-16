# 贡献指南

感谢参与。先读一眼 [PRIVACY.md](./PRIVACY.md)——本项目的数据边界是硬约束，不是建议。

## 本项目现在处于什么阶段

**产品定位已定，第一版还没写。** README 第一节的四步目标里，"开源积攒 star"排在"解决自己的痛点"之后。

所以现在最缺的不是功能，是**对定位的挑战**：

- 你认为它该解决另一个问题 → 开 issue 说，别自己改
- 你认为 README 里某个判断是错的 → 开 issue 指出，附证据
- 你想直接实现某个功能 → 先开 issue 确认它不违反第三节的"不是什么"

**尤其是第三种**：这个项目最可能的死法是功能长胖，跑偏成"GitHub 数据导出器"或"述职工具"。README 第三节把这两条列为红线。

## 硬约束

| 约束 | 原因 |
|---|---|
| **不引入云端 / 账号体系 / 遥测** | 与产品承诺直接冲突，见 PRIVACY.md |
| **不上传任何用户数据** | 同上。这条没有例外 |
| **不把真实私有仓数据提交进仓库** | 包括 git 历史。公开仓的历史等于永久公开 |
| PR 必须走 review | 单人项目也走。自己 review 自己，但要有记录 |
| 不做"通用化抽象层" | 见 README 第八节。倾向明说限制，而不是加抽象层 |

## commit 风格

英文、Conventional Commits、祈使句、≤72 字符。

```
feat(scripts): add repo signal measurement
fix(viz): normalize repo key before lane assignment
docs: clarify why score cannot prune traversal
```

## 开发

```bash
# Python 脚本
python3 scripts/measure_repo.py --help

# Go 实验
cd experiments/<name> && go run .
```

跑任何脚本之前，**确认 `gh` 登录的是你自己的主号**。
用 agent 沙盘小号跑出来的数据跟主号是完全两批，结论会整个反过来（这个坑踩过）。

## 报告问题时请附

- 你用的 `gh` 版本和账号类型（个人 / 组织）
- 仓库规模（大致 PR / issue 数就行，不用具体名单）
- 你看到的现象，以及你期望看到什么

**不要贴真实仓库名、PR 标题、内部路径。** 描述成 `<org>/<repo> #123` 就行。
