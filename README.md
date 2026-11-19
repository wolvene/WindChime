# WindChime

WindChime 是一个基于 Python 3 开发的伪MySQL Server 实现，它启动一个伪装成 MySQL 服务端的监听器，当客户端连接并执行查询时，利用 MySQL 协议的LOCAL INFILE机制请求客户端本地文件，将文件内容回传到服务端并保存。

> **免责声明**：本项目仅用于你拥有明确授权的安全测试、CTF 竞赛或协议研究场景。请勿在未授权的系统上使用。

## 功能特性

- **单文件 / 批量检索**：`-f` 指定单个目标文件，`-l` 从文本文件读取文件列表（每行一个，自动忽略空行）。
- **重试与自动跳过**：客户端拒绝或无法提供文件时自动重试，达到 `-a` 指定次数后跳过并请求下一个文件。
- **可配置监听端口与保存目录**：`-p` 指定端口，`-o/--save-dir` 指定下载目录。
- **并发连接处理**：基于 `asyncio`，可同时服务多个客户端连接。
- **协议兼容性**：复刻 MySQL 5.6.28 握手报文与报文序号规则，兼容 `mysql` CLI、libmysql、JDBC、PyMySQL 等常见客户端。
- **路径穿越防护**：保存时只取文件名的 basename，避免客户端提供的路径写到目录之外。
- **日志与调试**：文件日志默认写入 `log/windChime.log`；`-v` 输出到控制台，`-d` 开启 DEBUG 级别。

## 工作原理

1. 服务端在指定端口监听，向连入的客户端发送 MySQL 握手报文（HandshakeV10）。
2. 客户端响应认证（服务端不校验凭据），服务端回复 OK 报文完成认证。
3. 客户端执行 SQL 查询（`COM_QUERY`），服务端返回 `LOCAL INFILE` 请求，指定要读取的文件名。
4. 客户端将文件内容以一个或多个 MySQL 报文发回（每个报文 payload 最大 16MB-1，大文件由客户端自动分包）。
5. 服务端把报文 payload 追加写入下载目录；收到空 payload 报文表示本次传输结束。
6. 若客户端未回传任何内容，视为一次失败并重试同一文件；超过重试上限则跳过。随后自动请求下一个文件。
7. 所有任务结束后发送 OK 报文，随后立即以 RST 强制断开连接并终止服务进程；不会应答客户端后续的任何查询。

报文序号严格遵循 MySQL 协议：每个命令周期从 0 开始，服务端回复占用下一个序号，文件数据报文连续递增。

## 环境要求

- Python 3.10 或更高版本
- 第三方依赖：`rich`、`pyfiglet`（启动横幅与控制台输出）

安装依赖：

```bash
pip install rich pyfiglet
```

## 快速开始

在项目目录下运行：

```bash
# 请求单个文件
python windchime.py -f passwd

# 请求文件列表，指定端口、重试次数和保存目录
python windchime.py -l targets.txt -p 3306 -a 5 -o D:/loot

# 输出详细日志
python windchime.py -f /etc/passwd -v -d
```

查看所有参数：

```bash
python windchime.py --help
```

## 命令行参数

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `-p PORT` | 监听端口 | `3306` |
| `-f FILENAME` | 指定单个目标文件 | 无 |
| `-l FILELIST` | 目标文件列表文件（每行一个） | 无 |
| `-o, --save-dir DIRECTORY` | 下载内容保存目录 | `./Downloads` |
| `-a ATTEMPTS` | 每个文件放弃前的最大请求次数 | `3` |
| `-v` | 在控制台输出日志 | 关闭 |
| `-d` | 启用 DEBUG 日志级别 | 关闭 |

`-f` 与 `-l` 必须提供其一；端口范围 1–65535，`-a` 至少为 1。

## 项目结构

```
WindChime/
├── windchime.py           程序入口与生命周期管理
├── config.py              命令行参数解析与配置校验
├── logger.py              日志配置（文件 + 可选控制台）
├── exceptions.py          项目异常类型
├── connection/
│   ├── listener.py        TCP 监听器与连接管理
│   └── mysql_handler.py   会话处理：握手、LOCAL INFILE、文件接收、重试
├── protocol/
│   ├── packet.py          MySQL 报文封装与解析
│   └── constants.py       协议常量与握手/OK/EOF 报文构造
├── state_machine/
│   ├── states.py          协议/会话/操作状态枚举
│   └── machine.py         状态机与转换规则
├── file_manager/
│   ├── task_manager.py    文件任务状态与重试计数
│   └── file_handler.py    安全路径解析与文件写入
├── Downloads/             默认下载目录
└── log/                   默认日志目录
```

## 输出与日志

- 下载的文件保存在 `Downloads/`（或 `-o` 指定的目录），文件名取客户端路径的最后一段。
- 运行日志写入 `log/windChime.log`，格式包含时间戳、级别与消息。
- 控制台输出关键事件：`[+] Requesting ...`（请求文件）、`[+] File ... obtained`（接收成功）、`[-] Retrying ...`（重试）、`[-] Moving on from ...`（放弃）。

## 行为说明

- **同名文件采用追加写入**：如果保存目录中已存在同名文件，新内容会追加到文件末尾。如需干净落盘，请先清空目标目录。
- **任务完成后强制中断连接**：所有文件接收或放弃后，程序发出 OK 报文即通过 RST 强制切断连接并退出，不再应答客户端的任何后续查询。这与原版 RogueSQL 的 `sys.exit(0)` 行为一致：业务系统客户端会因连接重置而报错，连接流程异常终止，不会继续走完安装流程（例如写出程序锁）。
- **认证不校验凭据**：任何发起握手并响应的客户端都会被视为认证通过。

## 致谢

本项目重构自 Rogue-MySQL-Server，协议行为与握手报文格式沿用原实现，并在其基础上改为 Python 3 + asyncio 架构，修复了报文头部、序号管理和文件写入等问题。
