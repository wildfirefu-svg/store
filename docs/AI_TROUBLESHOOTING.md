# AI 服务连接排查

## 支持的 Key

- DeepSeek：`DEEPSEEK_API_KEY` 或项目根目录 `.deepseek_key`
- Anthropic：`ANTHROPIC_API_KEY` 或项目根目录 `.anthropic_key`

## 推荐启动方式

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

## 健康检查

打开：

```text
http://127.0.0.1:8000/api/health
```

如果健康检查失败，先修复后端启动问题，不要先排查模型服务。

## 前端显示“AI 服务连接失败”

该提示通常表示浏览器没有收到完整有效的 SSE 内容。常见原因：

1. 后端未启动或端口错误。
2. 未配置 `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY`。
3. Key 无效、过期或没有权限。
4. 账户余额或额度不足。
5. 当前网络无法访问 DeepSeek/Anthropic API。
6. 模型接口返回非 200。
7. 代理或网关中断了 `text/event-stream`。

## 排查顺序

1. 访问 `/api/health`。
2. 确认启动后端的同一个终端里有 key。
3. 查看后端日志里的 HTTP 状态码。
4. 如果是 401，重新配置 key。
5. 如果是 402 或余额提示，检查账户额度。
6. 如果是 429，降低请求频率或等待限流恢复。
7. 如果是超时，检查网络、代理和模型服务状态。

## 本地 key 文件

项目支持从根目录读取：

- `.deepseek_key`
- `.anthropic_key`

这些文件不得提交到 Git。
