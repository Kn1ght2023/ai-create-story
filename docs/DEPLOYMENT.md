# 服务器部署与上线手册

状态：当前代码的受保护单人部署可参考本文；本地优先多用户服务仍在规划，必须先完成本地存储、备份迁移、无正文落盘生成、多用户额度、断线恢复和上线验收后才能开放；内部实施计划不随公开仓库分发。本文不执行任何服务器变更。

## 1. 两种部署目标

当前程序：项目在服务器 `storys/` 下、API 配置全局共享、当前项目与任务锁全局共享、接口没有登录权限保护。加反向代理密码只能用于单人受保护使用，不能提供多用户数据隔离，也不满足“小说只存用户本地”。

目标公共服务：浏览器保存小说，服务器只临时处理内容并持久化身份/任务元数据/用量。MVP-06 验收前禁止公开注册。下文当前版的命令不会自动实现目标模式。

初期使用单台 Linux + 单实例 Go + Nginx + systemd。模型在外部供应商运行，本服务器不需要为本地模型配置 GPU。容量取决于任务上下文、并发和缓存限额，先测量再选择规格。

## 2. 构建与检查

在可信构建环境中准备 Go 1.25.1 或项目确认兼容的后续版本、兼容 Vite 5 的 Node.js/npm。仓库跟踪 frontend/package-lock.json，发布构建使用 npm ci 安装锁定依赖。

```bash
cd frontend
npm ci
npm run build
cd ..
go build ./...
go test ./...
go vet ./...
```

构建 Linux amd64 发布产物（版本号示例，每次发布使用唯一标识；arm64 服务器改 GOARCH）：

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags '-X main.version=mvp-preview-20261007' -o /tmp/show-me-the-story-linux-amd64 .
```

前端产物已嵌入，不需要在服务器上运行 Vite。正式版本不要使用默认 dev 版本号，以免启用开发日志。以下只在服务器执行，不在本机照搬 sudo 命令。

## 3. 当前版：受保护单人部署

### 3.1 创建独立用户与目录

服务器预先安装 Nginx、systemd 与提供 htpasswd 命令的软件包；安装方式依发行版执行。以管理员身份：

```bash
sudo useradd --system --home-dir /var/lib/show-me-the-story --shell /usr/sbin/nologin storyapp
sudo install -d -o root -g root -m 0755 /opt/show-me-the-story/releases/preview-20261007
sudo install -d -o storyapp -g storyapp -m 0700 /var/lib/show-me-the-story
sudo install -o root -g root -m 0755 /tmp/show-me-the-story-linux-amd64 /opt/show-me-the-story/releases/preview-20261007/show-me-the-story
sudo ln -sfn /opt/show-me-the-story/releases/preview-20261007 /opt/show-me-the-story/current
```

上传产物后核对文件校验和；二进制路径中的版本应与实际发布一致。当前程序通过目录参数确定数据根，PORT 只能填数字，不能写 `127.0.0.1:48090`，否则当前 main.go 会错误拼接地址。

### 3.2 systemd 服务

创建 `/etc/systemd/system/show-me-the-story.service`：

```ini
[Unit]
Description=Show Me The Story private preview
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=storyapp
Group=storyapp
WorkingDirectory=/var/lib/show-me-the-story
Environment=PORT=48090
ExecStart=/opt/show-me-the-story/current/show-me-the-story /var/lib/show-me-the-story
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/show-me-the-story
LimitCORE=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now show-me-the-story
sudo systemctl status show-me-the-story
curl --fail http://127.0.0.1:48090/api/version
```

当前版没有专用 healthz/readyz，version 只能确认 HTTP 进程可响应，不能确认模型和数据就绪。当前没有优雅任务恢复保证，重启前应在界面停止任务并确认保存。

### 3.3 防火墙、域名与 TLS

将正式域名指向服务器，配置有效 TLS 证书及自动续期。证书申请依 DNS/服务商完成；下面假定证书已位于示例路径，替换为实际域名和证书路径后再启用。

当前 Go 监听所有接口，必须在主机防火墙和云安全组拒绝公网 TCP 48090，仅开放业务 80/443 和受限管理入口；不要关闭唯一 SSH 入口。代理与应用放在同机。防火墙不足以阻止本机其他不可信进程，服务器也必须隔离管理权限。

创建代理密码文件（交互输入，不把密码放进命令行）：

```bash
sudo htpasswd -c /etc/nginx/story.htpasswd author
```

确保 Nginx worker 可读该文件；后续新增账户不要再用 `-c`，以免覆盖。此处只创建一个私有操作者账号，不代表应用已有多用户权限。

Nginx 示例：

```nginx
server {
    listen 80;
    server_name story.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name story.example.com;
    ssl_certificate /etc/letsencrypt/live/story.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/story.example.com/privkey.pem;

    auth_basic "Private story preview";
    auth_basic_user_file /etc/nginx/story.htpasswd;
    client_max_body_size 2m;
    # 当前版导入超过此值会返回 413，确认实际需要后有界调整。
    # 禁止请求正文缓冲到临时磁盘；过大请求拒绝处理。
    client_body_buffer_size 2m;
    client_body_in_file_only off;

    location / {
        proxy_pass http://127.0.0.1:48090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        # 不把代理登录凭证传给应用或上游。
        proxy_set_header Authorization "";
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        proxy_max_temp_file_size 0;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

120 秒是两次上游读取之间的超时，不是整章最长时间；目标版需有小于该间隔的心跳，例如 15 秒。当前版长时间无事件可能断线，应在私有环境实测，不能无限提高超时来代替心跳。

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -I https://story.example.com/
curl --user author https://story.example.com/api/version
```

首个请求预期 401；第二个交互输入密码后预期正常响应。从另一台公网设备检查 48090 不可访问。随后登录界面配置模型；不要把 api.json、凭证或小说上传到 Git。

## 4. 目标版：本地优先邀请服务部署差异

本节是发布验收约定，不是现有可执行配置。具体启动参数、路由和认证网关配置必须在 MVP-04/06 实现后回填；目前不存在 PUBLIC_MODE、LISTEN_ADDR、healthz 等可直接使用的开关，不要自行假定它们生效。

- 应用显式启用公共模式并监听 loopback；旧项目文件/API 配置/全局事件接口不注册。认证网关必须实际验证身份并覆盖外部身份头，不能直接信任浏览器传来的 user_id。
- 上节 Basic Auth 仅用于单人预览，不能替代目标版身份协议。若沿用 Nginx Basic Auth 作为邀请身份源，须新增应用可验证的身份传递协议、账户停用、CSRF 和逐任务授权并完成越权测试；不得只增加一个代理头就开放。
- 使用正式同源 HTTPS 域名；Cookie 会话如采用则配置 Secure/HttpOnly/SameSite，事件流不能把凭证放在 URL。CORS 不使用任意来源。
- 平台密钥由受限服务配置加载，API 响应只返回模型别名/可用性。MVP 不开放任意供应商 URL。
- 请求体与内存限额同时在代理和应用强制执行。请求缓冲、响应缓存、WAF/APM 采样、崩溃转储均不得保存小说内容；审查供应商错误与 stderr。
- Linux swap 可能把内存内容写盘。若承诺服务器不落盘处理内容，应禁用或采用符合该承诺的内存/磁盘策略，并限制服务内存以防 OOM；不能仅依靠不调用 WriteFile 宣称“绝不落盘”。
- 为事件流提供心跳和短重连窗口；内存缓存达到上限或 TTL 时取消并通知。队列只保留内存快照，重启后任务中断。
- 提供 health/ready 检查：ready 不发收费模型请求；配置缺失、账本不可写或退出中时不就绪。
- 元数据目录只包含用户、配额、任务状态、账本和受限配置。若发现 storys/ 出现正文或临时 JSON，应阻止上线并调查写入路径。
- 单实例账本与锁不得直接共享给多个副本；扩容到多实例前重新设计预算原子性、任务路由与存储。

## 5. 发布验收与日常运行

首次上线：

1. 构建/测试通过，记录版本、产物校验和、运行配置及各 MVP 验收结果。
2. 验证公网端口、TLS、未登录拒绝、跨用户任务拒绝和旧接口拒绝。
3. 用唯一内容标记生成一章，检查应用目录、临时目录、日志、代理目录和备份没有该内容；此演练仅是检测证据，还须审计所有写入路径。
4. 两位邀请用户并发，确认内容/任务隔离、预算上限和内存高水位。
5. 演练断网、重连窗口耗尽、取消、进程重启、本地存储失败。
6. 设备 A 导出完整项目，设备 B 导入并续写；检查正文、记忆和伏笔一致。
7. 演练管理员关闭新任务、服务回滚、元数据恢复。

日常观察任务成功率、上游错误率、取消耗时、额度结算异常、排队时间、内存及磁盘用量；监控标签不含作品标题/正文/用户提示词。容量压测使用模拟模型，供应商联调另设小额预算。

## 6. 备份、升级与回滚

当前私有版备份：停止任务并停止服务后，以加密受限备份复制 `/var/lib/show-me-the-story`，包括 api.json 与 storys/；恢复演练在隔离环境执行，注意备份含真实密钥和小说。

目标版备份：只备份账号/配额/用量/任务元数据及受限配置；先停止接新任务，等待或取消活动任务，安全停止写者再做一致快照。恢复账本时核对快照之后已发生的供应商调用，避免回滚额度导致重复消费。不要备份内存内容缓存。

用户小说：浏览器本地自动保存，用户导出 `.storyproj` 才能跨设备迁移。服务端备份无法找回小说。域名/协议/端口变化会改变存储 origin；迁站前在旧域名提醒导出并保留迁移窗口，不能用 HTTP 重定向自动搬走 IndexedDB 数据。

升级：先在测试环境验证本地 schema 兼容，部署新版本到新的 release 目录，停接任务、排空或取消，再停止服务、切换 current 链接并启动；验收失败停止服务并切回已验证版本。不要覆盖唯一旧二进制。

回滚：服务二进制可以切回，但前端已升级的 IndexedDB 与服务端账本也要兼容；不兼容时使用预先设计的迁移/恢复方案，禁止让旧前端静默清库。恢复用户项目应以新本地项目导入，避免覆盖唯一副本。

## 7. 常见问题

- 构建提示找不到本模块包：检查 GO111MODULE 是否被全局设为 off，可仅对当前命令设置 `GO111MODULE=on`；不要修改用户全局配置。若随后提示无法下载/校验 Go 工具链，应在有网络的可信构建环境准备 Go 1.25.1，不要关闭校验来绕过。
- 502：检查 systemd 状态、PORT、二进制架构和代理目标；不要先开放后端端口。
- SSE 一次性出现：检查代理/CDN 缓冲和压缩，确认心跳、超时及事件路由。
- 413：请求超过限额；优先减少写作上下文，不把全书上传；完整项目导入应在浏览器执行。
- 刷新后项目消失：检查是否换域名、浏览器配置或隐私模式；尝试备份包恢复。不要删除 IndexedDB 作为首个排错步骤。
- 重启任务中断：目标 MVP 的预期行为，从本地草稿/检查点重试，不能声称服务器能找回未发送结果。

## 参考

- [Nginx proxy 模块](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)：缓冲、代理超时与临时文件。
- [systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)：服务生命周期与重启。
- [MDN 存储配额与清理](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)：IndexedDB 容量、清理和持久存储边界。

以上部署配置是待管理员按实际环境核对的示例，当前会话没有在 Linux 服务器实测或部署。
