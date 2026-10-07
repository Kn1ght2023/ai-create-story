# 公开仓库文件范围

本文件说明公开内容与本地资料的边界，不表示已完成推送或完整历史安全审计。

## 应提交

- Go 源码、go.mod、领域与 HTTP/LLM 等测试。
- frontend 源码、package.json、package-lock.json、Vite/Svelte 配置和入口。
- internal/story/embeds/skills：程序会嵌入的内置技能，必须保留。
- scripts/model_fingerprint：可复用的独立检测工具、说明与测试；不包含个人运行报告。
- .github 发布工作流、Taskfile.yml、.gitignore、LICENSE。
- 中英文 README、截图、公开部署与贡献文档。

非运行时文件不等于不应公开：测试、锁文件、许可证、构建和用户文档是可复现项目的一部分。

## 仅保留本地

- `.local/development/`：内部开发计划与 MVP 节点。
- `.local/test-data/`：个人测试小说、导出目录与压缩包。
- `.local/archive/`：未被当前构建引用的历史页面。
- 根目录 `AGENTS.md`：个人 AI 工作说明，取消跟踪但保留文件。
- `api.json`、`storys/`、`fingerprint_runs/`、日志、项目备份、环境凭证。
- node_modules、dist、可执行文件、缓存和操作系统元数据。

新增个人资料统一放到 `.local/`；需要公开的测试 fixture 使用合成数据并随测试代码提交。不要用全局 `*.json` 或 `*.md` 忽略规则误伤依赖清单、示例和文档。压缩包也不一概忽略：私有导出归入 .local，公开资源需明确用途。

## 提交前检查

```bash
git status --short
git diff --check
git diff --cached --name-status
git ls-files AGENTS.md api.json 'storys/*' 'fingerprint_runs/*' '.local/*'
git check-ignore -v api.json storys/example/progress.json .local/test-data/example.txt
```

取消跟踪后，ls-files 不应返回上面的本地资料。检查 Git diff 时注意当前修改可能包含其他尚未提交的功能工作，不要盲目整仓提交。

.gitignore 只影响未跟踪文件，不能从旧提交移除内容。若密钥曾进入任何提交，应撤销/轮换密钥；公开历史前另做历史检查，必要时设计历史清理。不在整理过程中自动改写历史或推送现有远程。
