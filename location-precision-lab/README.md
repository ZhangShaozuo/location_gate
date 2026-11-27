# 定位精度实验台

输入意图与位置槽位后，页面显示模型标签、实际返回的 JSON，以及 Android 传统网格和 S2 网格对同一模拟坐标的处理结果。包含 76 个可载入样例、35 个地点预设和悬浮说明。`dist/` 是完整静态网站，内含由 356 个归一化语义组合拟合的演示模型和对应规则参考。实验台使用模拟坐标、城市和人口密度，判定在浏览器内完成。

## Linux 本地运行

需要 Python 3.10 或更新版本。从仓库根目录启动：

```bash
python3 location-precision-lab/serve.py --port 8080
```

在运行服务的电脑打开 <http://127.0.0.1:8080/>。终端按 `Ctrl+C` 停止。端口被占用时，可将 `8080` 改为 `8081`。

需要用 Node.js 运行现有模型、规则和网格测试时，在仓库根目录运行：

```bash
node --test location-precision-lab/test/location-policy.test.mjs
```

## 从远端电脑访问

如果实验台运行在 Linux 服务器，且你已有 SSH 权限，先在服务器启动上述命令，再在自己的电脑运行：

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8080:127.0.0.1:8080 shaozuo@SERVER_HOST
```

把 `SERVER_HOST` 换成服务器地址，保留 SSH 会话，在自己的电脑打开 <http://127.0.0.1:8080/>。如果自己的 8080 端口已占用，可以只改 `-L` 中第一个端口，浏览器也使用这个端口。

## 分享选项

| 受众 | 部署方式 |
| --- | --- |
| 自己或已有服务器访问权限的同事 | 保持监听 `127.0.0.1`，每人用自己的 SSH 账号建立上述转发。 |
| 公司内网团队 | 让已有登录控制的 HTTPS 静态站点托管 `location-precision-lab/dist/`。使用 Tailscale 的团队也可用 `tailscale serve --bg 8080`，并按团队策略授予访问权限。 |
| 可公开访问的演示 | 选择 GitHub Pages 或现有静态托管平台，将 `location-precision-lab/dist/` 作为发布目录。GitHub Pages 的自定义工作流可将该目录作为 Pages 构建产物。 |

本地启动脚本面向开发和 SSH 转发。共享静态站点时，浏览器会下载演示模型和预设数据，发布前应确认这些内容适合目标受众。HTTPS 和本机 `localhost` 可用于浏览器的「复制 JSON」功能。

- [OpenSSH 端口转发](https://man.openbsd.org/ssh.1)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [GitHub Pages 发布来源与自定义工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
