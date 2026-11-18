# Luz Project 经验

项目编排的经验保存在 `notes.json`：用户新说的偏好、规则纠正、踩过的坑、有效做法。密钥、客户名称和生产数据不进入这里。

```powershell
python -X utf8 scripts/experience.py search 审批 哈希
python -X utf8 scripts/experience.py note --kind lesson --key project-stage-hash --text "上游产物哈希变化时必须让下游审批回到待复核。" --why "依据"
python -X utf8 scripts/experience.py note --kind preference --key <主题> --text "<要求>" --scope project
python -X utf8 scripts/experience.py check
```

- 同一个 key 再写一次：文字相同是确认（次数加一），文字不同是替换，旧文字留作上一版。
- 只属于某个项目或某次会话的要求加 `--scope project`，正文写明是哪个项目；维护本技能自身的经验加 `--scope maintenance`。
- 规则已经写进手册或共享合同的，加 `--codified "<文件 › 小节>"`，以那份正文为准。
- `search` 可以给多个词，全部命中才返回。
