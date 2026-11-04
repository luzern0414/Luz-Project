# Luz Project experience

通用的项目编排经验保存在 `notes.json`。项目特定信息、密钥、客户名称和生产数据不进入这里。

## 使用

```powershell
python -X utf8 scripts/experience.py search "审批"
python -X utf8 scripts/experience.py note --kind lesson --key project-stage-hash --text "上游产物哈希变化时必须让下游审批回到待复核。"
python -X utf8 scripts/experience.py check
```
