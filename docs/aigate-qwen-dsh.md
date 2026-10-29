# AIGate Qwen3.6 与本地 DeepSeek Harness 运维记录

本文记录在 AIGate GPU 实例上运行 Qwen3.6 GGUF，并让本机源码版 DeepSeek Harness（DSH）通过 OpenAI 兼容 API 使用该模型的完整流程。

本指南固定使用 AIGate **华东二区**；实例 ID、GPU SKU、镜像 ID、SSH 地址和服务端口仍需运行时查询。

## 参考配置

| 项目 | 配置 |
| --- | --- |
| AIGate 区域 | 华东二区 |
| 模型 | `Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf` |
| 模型目录 | `/home/waas/models/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive/` |
| llama-server 内部端口 | `127.0.0.1:6007` |
| API 代理内部端口 | `0.0.0.0:6006` |
| 上下文 | `262144` tokens（256K） |
| DSH 输出上限 | `32768` tokens（32K） |
| 本地 DSH Web | `http://127.0.0.1:3080` |

AIGate 的 SSH 域名、映射端口和 HTTP 6006 域名可能随实例重新分配而变化，不要把它们当作永久值。实例被 `release` 后，实例磁盘上的模型文件也不应再视为可保留数据。

## 1. 开启已有 AIGate 实例

在本机 OPC 仓库执行。项目的 `.venv` 必须先激活：

```bash
cd /Users/apple/Documents/github/OPC
source .venv/bin/activate

export AIGATE_INSTANCE_ID='<已有实例 ID>'
opc aigate --status
opc aigate --start --instance "$AIGATE_INSTANCE_ID" --ready-timeout 300
```

状态 `运行中(2)` 表示实例已运行。`--start` 只启动已有实例，不会新建计费资源。

如果需要新建实例，必须先刷新华东二区的 GPU SKU 和个人镜像：

```bash
opc aigate --gpus --area 华东二区
opc aigate --images
```

然后显式提供当前可用的 SKU、华东二区、镜像 ID 和镜像类型：

```bash
opc aigate --start --create \
  --sku '<当前可用 SKU>' \
  --area '华东二区' \
  --image-id '<当前镜像 ID>' \
  --image-type 3
```

不要使用 `--release` 代替 `--stop`。`release` 是删除实例资源的操作。

## 2. 获取当前 SSH 和 API 地址

AIGate 控制台 API 会返回当前实例的服务映射。以下命令只打印非敏感的主机、端口和 HTTP 地址，不打印 Token 或 SSH 密码：

```bash
cd /Users/apple/Documents/github/OPC
source .venv/bin/activate
set -a
source .env
set +a

python3 -c '
from opc_cli.aigate import get_instance_detail
import os

d = get_instance_detail(os.environ["AIGATE_TOKEN"], os.environ["AIGATE_INSTANCE_ID"])
for service in d.get("instanceUtilList", []):
    if service.get("name") in ("ssh", "HTTP 6006"):
        print(service.get("name"), service.get("host"), service.get("instancePort"))
'
```

如果本机已配置 SSH key，直接使用查询到的 `host` 和 `instancePort`：

```bash
ssh -p '<当前 SSH 映射端口>' root@'<当前 SSH 主机>'
```

如果该实例只提供 AIGate 返回的密码，可临时从实例详情取出密码放入 `SSHPASS` 环境变量，用完立即清除。不要把密码写入本文档、Shell 历史或 Git：

```bash
export AIGATE_SSH_PASSWORD=$(python3 -c '
from opc_cli.aigate import get_instance_detail
import os
d = get_instance_detail(os.environ["AIGATE_TOKEN"], os.environ["AIGATE_INSTANCE_ID"])
s = next(x for x in d["instanceUtilList"] if x.get("name") == "ssh")
print(s.get("password") or "", end="")
')

SSHPASS="$AIGATE_SSH_PASSWORD" sshpass -e ssh \
  -p '<当前 SSH 映射端口>' \
  root@'<当前 SSH 主机>'

unset AIGATE_SSH_PASSWORD SSHPASS
```

## 3. 容器内模型文件

模型和视觉投影文件位于实例的 `/home/waas`，不是 Docker 镜像层：

```bash
MODEL_DIR=/home/waas/models/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive
MODEL="$MODEL_DIR/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf"
MMPROJ="$MODEL_DIR/mmproj-Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-f16.gguf"

ls -lh "$MODEL" "$MMPROJ"
```

下载或检查模型时，可以在当前 SSH 终端启用 AIGate 网络代理：

```bash
source /etc/waas-script/proxy.sh
```

该代理只对当前终端生效。

## 4. 启动 Qwen llama-server

当前配置使用 Q6_K_P 模型、f16 mmproj、256K 上下文和 q8 KV cache。启动前先确认没有重复的 llama-server：

```bash
ps -eo pid,etime,args | grep -E 'llama-server|qwen-proxy' | grep -v grep
nvidia-smi
```

停止已确认的旧 llama-server PID。只终止确认过的模型进程，不要按宽泛关键字杀进程：

```bash
kill -TERM '<已确认的 llama-server PID>'
```

启动模型服务：

```bash
MODEL_DIR=/home/waas/models/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive

nohup /home/waas/llama.cpp/build/bin/llama-server \
  -m "$MODEL_DIR/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf" \
  --mmproj "$MODEL_DIR/mmproj-Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-f16.gguf" \
  --host 127.0.0.1 \
  --port 6007 \
  --api-key-file /home/waas/qwen-api.key \
  --alias qwen3.6-27b-aggressive \
  --ctx-size 262144 \
  --parallel 1 \
  -ngl 99 \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --jinja \
  --no-webui \
  > /home/waas/llama-server-256k.log 2>&1 </dev/null &
```

模型服务就绪的关键日志是：

```text
n_ctx_slot = 262144
llama_server: model loaded
llama_server: listening on http://127.0.0.1:6007
```

检查状态和显存：

```bash
curl -sS http://127.0.0.1:6007/health
tail -n 40 /home/waas/llama-server-256k.log
nvidia-smi
```

256K 配置需要足够的显存；长上下文、图片输入、并发请求和 32K 输出都会继续增加显存压力。遇到 CUDA OOM 时，优先降到 131072 或减少输出上限。

## 5. 启动 6006 API 代理

`qwen-proxy.py` 负责将外部 HTTP 6006 服务转发到内部 llama-server 6007，并校验 `/v1` 请求的 Bearer key。先检查是否已经运行：

```bash
ps -eo pid,etime,args | grep qwen-proxy | grep -v grep
ss -ltnp | grep -E ':6006|:6007'
```

如果代理未运行，再启动一个实例：

```bash
nohup python /home/waas/qwen-proxy.py \
  > /home/waas/qwen-proxy.log 2>&1 </dev/null &
```

不要重复启动多个代理。AIGate 的 HTTP 6006 服务地址就是本地 DSH 的 `baseURL` 去掉末尾 `/v1` 后的地址。

## 6. 验证外部 OpenAI 兼容 API

从本机获取当前 HTTP 6006 地址：

```bash
export AIGATE_HTTP_HOST=$(python3 -c '
from opc_cli.aigate import get_instance_detail
import os
d = get_instance_detail(os.environ["AIGATE_TOKEN"], os.environ["AIGATE_INSTANCE_ID"])
s = next(x for x in d["instanceUtilList"] if x.get("name") == "HTTP 6006")
print(s["host"].split("?", 1)[0], end="")
')
export QWEN_BASE_URL="https://${AIGATE_HTTP_HOST}"
```

健康检查不需要 key；模型列表和推理请求需要 key：

```bash
curl -sS "$QWEN_BASE_URL/health"

QWEN_KEY=$(sed -n 's/^LOCAL_QWEN_API_KEY: //p' /Users/apple/.dsh/.credentials.yaml)
curl -sS "$QWEN_BASE_URL/v1/models" \
  -H "Authorization: Bearer $QWEN_KEY"
```

预期模型 ID 为 `qwen3.6-27b-aggressive`。不要在终端输出、文档或提交中打印 `QWEN_KEY`。

## 7. 配置本地 DSH

DSH 使用用户级配置，不修改 `deepseek-harness` 仓库。配置文件：

```text
/Users/apple/.dsh/settings.yaml
/Users/apple/.dsh/.credentials.yaml
```

确保 `.credentials.yaml` 权限为 600，并包含与 `/home/waas/qwen-api.key` 相同的本地适配凭据名 `LOCAL_QWEN_API_KEY`。不要把真实值写进仓库。

在 `/Users/apple/.dsh/settings.yaml` 中使用以下路由结构；将 `<当前 HTTP 6006 主机>` 替换为运行时查询到的地址：

```yaml
agent-default-model:
  provider: local-qwen
  model: qwen3.6-27b-aggressive

llm-pi-ai:
  providers:
    local-qwen:
      displayName: Local Qwen3.6
      apiKeyEnv: LOCAL_QWEN_API_KEY
      api: openai-completions
      baseURL: https://<当前 HTTP 6006 主机>/v1
      models:
        - id: qwen3.6-27b-aggressive
          contextWindow: 262144
          maxTokens: 32768
          input: [text, image]
```

`contextWindow` 必须和 llama-server 的 `--ctx-size` 对齐。上下文是输入和输出合计；当前 256K 上下文与 32K 输出上限组合时，实际可用输入约为 224K tokens。

Qwen 的识图能力由主模型 GGUF 与 `--mmproj` 视觉投影文件共同提供；启动 llama-server 时带上 `--mmproj` 只表示远端接口具备多模态能力。DSH 对用户手动声明的模型默认按纯文本模型处理，不会自动探测接口是否接受图片，因此必须在对应模型条目中声明 `input: [text, image]`。缺少该字段时，DSH 会在图片发送前拒绝 `read_image`，并显示“当前模型不支持直接读取图片”，请求不会到达远端 Qwen。

如果通过 SSH 隧道访问 6006，应将 `baseURL` 改为本机隧道地址，例如 `http://127.0.0.1:16007/v1`；若使用 AIGate 提供的 HTTP 6006 公网映射，则使用上面的 `https://<当前 HTTP 6006 主机>/v1`。修改用户级配置后必须重启 DSH Web，使模型能力快照更新。

## 8. 启动本地 DSH Web

使用源码仓库启动完整 Web 应用，不要使用裸 `apps/web` Vite 开发服务器代替它：

```bash
cd /Users/apple/Documents/github/deepseek-harness
pnpm install          # 首次安装或依赖更新后执行
pnpm run build        # 首次运行或源码更新后执行
pnpm dsh web --port 3080
```

看到下面的输出才表示 Web 入口完成绑定：

```text
dsh web: http://127.0.0.1:3080
```

另开终端验证：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3080
```

预期返回 `200`。关闭服务使用当前前台终端的 `Ctrl-C`。

## 9. 常见故障

### SSH `Connection refused`

AIGate 重新分配实例后 SSH 主机或映射端口可能变化。重新执行第 2 节的服务查询，不要继续使用旧的 SSH 地址。

### API 返回 `404 Route Not Found`

通常是实例已经停止，虽然 OpenAPI 仍返回旧的服务域名。执行：

```bash
opc aigate --status
opc aigate --start --instance "$AIGATE_INSTANCE_ID"
```

### API 返回 401

确认远端 `/home/waas/qwen-api.key` 和本机 `.credentials.yaml` 中的 `LOCAL_QWEN_API_KEY` 是同一凭据；不要把 key 放进 URL。

### `request exceeds available context size`

检查三个值是否一致：

```bash
ps -eo pid,args | grep llama-server | grep -v grep
rg -n 'contextWindow|maxTokens' /Users/apple/.dsh/settings.yaml
tail -n 60 /home/waas/llama-server-256k.log
```

修改服务端 `--ctx-size` 后必须重启 llama-server；修改 DSH `settings.yaml` 后必须重启 DSH Web。输出上限也占用上下文空间。

### CUDA out of memory

先降低上下文或输出上限：

```text
--ctx-size 131072
contextWindow: 131072
maxTokens: 8192
```

三者应同步修改，并重新验证 `nvidia-smi`、`/health` 和实际聊天请求。

## 10. 性能测量

生成速度取决于 GPU、量化格式、上下文长度、KV cache 类型、并发数和输出长度。部署完成后，使用固定提示词和固定 `max_tokens` 做基线测试；不要把某一台实例上的速度当作所有实例的保证值。
