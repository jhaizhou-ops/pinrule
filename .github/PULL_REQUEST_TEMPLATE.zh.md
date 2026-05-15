## 这个 PR 做什么

简短描述改动。如果是新功能，说明对应规则层 / check 层 / hook 层哪一层。

## 驱动场景

karma 验证标准是「作者 / 用户能讲出 3 个具体案例」— 这个 PR 解决的场景是什么？

## 验证证据

- [ ] 测试全过：`pytest tests/ -q`
- [ ] 静态检查清干净：`ruff check karma/ tests/ && mypy karma/ tests/ && vulture karma/ --min-confidence 80`
- [ ] manual run 验证 hook 行为（如果改了 hook）
- [ ] 如果加规则模板 / check 函数，加对应测试

## 边界检查

- [ ] 不引入 LLM 依赖
- [ ] 不引入 retrieval / cosine / 评分系统
- [ ] 不破现有 `rules.yaml` 配置兼容
- [ ] 默认保持小、可 review；维护者明确要求「一个 PR 别拆碎」时一波到位也合理

## 相关

- 关联 issue: #
- 相关版本: （从 `karma --version` 看）
