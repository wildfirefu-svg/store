# 生产安全配置

## 必填环境变量

- `BAZI_ENV=production`
- `BAZI_API_KEY=<强随机密钥>`
- `BAZI_CORS_ORIGINS=https://your-domain.example`
- `BAZI_ALLOW_QUERY_API_KEY=0`

## API Key 传递方式

生产环境只允许：

```text
Authorization: Bearer <BAZI_API_KEY>
```

不要使用：

```text
?api_key=<BAZI_API_KEY>
```

query key 容易进入浏览器历史、代理日志、Referer 和监控系统。

## CORS

开发环境可以使用：

```powershell
$env:BAZI_CORS_ORIGINS="*"
```

生产环境必须显式配置域名，不应使用 `*`。

## 敏感数据

以下数据都应视为敏感数据：

- 出生日期、出生时间、出生地点
- 命主姓名和客户信息
- 聊天历史
- 分析报告
- 人生事件
- API key 与模型 key

生产日志不得记录完整 key、完整 prompt、完整出生信息或完整报告内容。

## 本地密钥文件

以下文件不得提交：

- `.deepseek_key`
- `.anthropic_key`
- `.bazi_api_key`
- `.env`
- `bazi_data.db`

## 发布前检查

```powershell
python -m pytest -q
git status --short
git ls-files .deepseek_key .anthropic_key .bazi_api_key .env bazi_data.db
```

最后一条命令应无输出。
