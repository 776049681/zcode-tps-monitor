# zcode-tps-monitor

macOS 菜单栏小工具：实时显示 ZCode **当前会话**正在使用的模型、**首字延迟**（精确到 0.1s）和 **TPS**（纯解码速率）。

只读本地 SQLite 数据库，**零权限、零注入、不修改 ZCode 本体**。

```
菜单栏：  FlashX 2.2s 146tps
          └ 模型 / 首字 / 纯解码TPS，随当前会话自动切换
```

## 特性

- **跟随当前会话**：右上角始终显示你最近发消息的会话的数据，多会话多模型互不混淆
- **首字延迟 0.1s 精度**：取该会话最近一次有效调用（一两 token 的短应答自动跳过，避免显示 "—"）
- **两种 TPS**：纯解码（扣除首字等待）与端到端分开显示
- **免费渠道标记**：start-plan 等免费渠道的 Flash 与付费渠道区分显示
- **今日汇总**：菜单里可看当天各模型的调用次数与平均 TPS
- **SessionStart 自动启动**：通过 ZCode 钩子随会话自动拉起，无需手动开
- **零权限**：不需要辅助功能、不需要屏幕录制、不注入会话上下文（钩子输出为 0 字节）

## 原理

ZCode CLI 会把每次模型调用写入 `~/.zcode/cli/db/db.sqlite`（`model_usage` 表含
`duration_ms / time_to_first_token_ms / output_tokens` 等）。本工具以只读方式
（`mode=ro`）每 2 秒查询一次：

- **当前会话** = `session` 表中 `time_updated` 最新的一条
- 首字 = `time_to_first_token_ms / 1000`，一位小数
- 纯解码 TPS = `output_tokens / ((duration_ms - time_to_first_token_ms) / 1000)`
- 端到端 TPS = `output_tokens / (duration_ms / 1000)`

## 安装

需要 macOS + Python 3（系统自带即可）。

```bash
git clone https://github.com/776049681/zcode-tps-monitor.git
cd zcode-tps-monitor
./install.sh --hook    # 建 venv、装依赖、把 SessionStart 钩子写入 ~/.zcode/cli/config.json
```

`install.sh --hook` 会先备份你的 `config.json` 为 `config.json.bak` 再合并，
不会破坏已有配置。不想用钩子的话，手动跑也行：

```bash
./install.sh
./venv/bin/python3 zmenu_tps.py
```

也可以把 `zmenu_tps.py` 设为 macOS 登录项，登录即常驻。

调试模式（不启动 GUI，直接打印当前状态）：

```bash
./venv/bin/python3 zmenu_tps.py --once
```

### 钩子配置长什么样

`install.sh --hook` 会在 `~/.zcode/cli/config.json` 里合并如下片段（手动配置可照抄，
把路径换成你自己的）：

```json
{
  "hooks": {
    "enabled": true,
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          { "type": "command", "command": "/path/to/zcode-tps-monitor/zmenu_tps_launcher.sh", "timeout": 5 }
        ]
      }
    ]
  }
}
```

注意：钩子命令的 stdout 会被注入会话上下文，`zmenu_tps_launcher.sh` 严格保证
0 字节输出，启动日志走 `$TMPDIR/zmenu_tps.log`。

## 已知边界

- **纯切换不跟随**：切到另一个会话但一条消息都不发时，右上角不变（`time_updated`
  只在真正交互时更新）。在新会话发出第一条消息后 2 秒内自动切过去。这是零权限
  方案的固有边界——"当前聚焦的是哪个会话"只存在于应用内存的 UI 状态里，进程外
  无信号可读（窗口标题恒为 "ZCode"，presence 表只在面板打开时写一次）。
- **schema 依赖**：表结构读自当前版本的 ZCode CLI，ZCode 后续大版本若改 schema
  需要同步更新 SQL。
- 仅在 macOS + Apple Silicon 上验证过，未测 Intel / 多用户场景。

## License

MIT
