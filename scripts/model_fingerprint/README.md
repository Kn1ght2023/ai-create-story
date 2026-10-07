# 大模型指纹检测器（MVP 脚本）

黑盒检测第三方 OpenAI Compatible 中转是否与声明模型行为大致一致。  
**不能**证明真实上游；报告仅使用：高度疑似 / 较为接近 / 无法确认 / 存在明显异常。

## 依赖

Python 3.10+，仅标准库（无需 pip）。

## 运行

在仓库根目录：

```bash
export FINGERPRINT_API_KEY='sk-xxx'   # 推荐：不要把 key 写进命令历史

python3 -m scripts.model_fingerprint \
  --provider-name HolySheep \
  --base-url 'https://api.holysheep.cn' \
  --model 'claude-sonnet-5' \
  --claimed-family claude \
  --mode standard \
  --repeats 3
```

或：

```bash
python3 -m scripts.model_fingerprint \
  --base-url 'https://api.deepseek.com' \
  --api-key "$FINGERPRINT_API_KEY" \
  --model 'deepseek-v4-flash' \
  --claimed-family deepseek \
  --mode quick
```

## 模式

| 模式 | 说明 |
|------|------|
| `quick` | 较快；Needle 缩到约 8K 字；仍含小说专项 |
| `standard`（默认） | 10 项核心 + Token + Stream；Needle 约 35K 字（估 50K+ tokens） |
| `deep` | 与 standard 相同测试集，Needle/Token 更重（仍非完整 100K×5 点，控费） |

强制跳过长上下文：`--no-long-context`  
跳过流式：`--no-stream`

## MVP 测试清单

1. T01 模型列表（弱信号）
2. T02 身份自述（权重极低）
3. T03 严格 JSON ×5
4. T04 冲突指令
5. T05 中文小说文风（全文落盘）
6. T06 尸魂意识流
7. T07 作者信息泄露（狄成）
8. T08 连续性
9. T09 长上下文 Needle（quick/standard 缩规模；见报告说明）
10. T10 同 Prompt 重复 ×N（默认 3）
11. T11 Token Usage 粗测
12. T12 Streaming 指纹（弱）

## 输出

`fingerprint_runs/<run_id>/`

- `report.md` / `report.json`
- `raw/*.json` 原始响应摘要
- `T05_novel.txt` 等全文供人工 Blind Review

API Key 只以 `sk-****xxxx` 出现在报告中，**不会**写入日志明文。

## 安全

- 后端脚本直连第三方；Key 用环境变量
- 不写 LocalStorage（本脚本无前端）
- 单次失败最多重试 2 次

## 后续（未实现）

Tool Calling、官方 A/B 对照、500K/1M、Web UI 集成、加密存储 Provider。
