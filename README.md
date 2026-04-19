# AI News Digest

多源并发汇总抓取工具，从 15 个科技新闻源采集数据，统一归一化、去重后输出 CSV。

## 数据源

| Source Name | 来源 | 类型 |
|---|---|---|
| `github_trending` | GitHub Trending | 网页抓取 |
| `hn_news` | Hacker News | API |
| `techcrunch_news` | TechCrunch | API |
| `verge_news` | The Verge | 网页抓取 |
| `wired_news` | Wired | 网页抓取 |
| `reuters_news` | Reuters | API |
| `scmp_news` | South China Morning Post | API |
| `tmtpost_news` | 钛媒体 | API |
| `kr36_news` | 36氪 | API |
| `ifanr_news` | 爱范儿 | API |
| `qbitai_news` | 量子位 | 网页抓取 |
| `pingwest_news` | 品玩 | 网页抓取 |
| `mtr_news` | 明天日报 | 网页抓取 |
| `wscn_news` | 华尔街见闻 | API |
| `x_tweets` | X (Twitter) | GraphQL API |

## 项目结构

```
├── main.py                          # 入口：调度、归一化、去重、输出
├── sources/                         # 各源抓取脚本
│   ├── github_trending.py
│   ├── hn_news.py
│   ├── techcrunch_news.py
│   ├── verge_news.py
│   ├── wired_news.py
│   ├── reuters_news.py
│   ├── scmp_news.py
│   ├── tmtpost_news.py
│   ├── kr36_news.py
│   ├── ifanr_news.py
│   ├── qbitai_news.py
│   ├── pingwest_news.py
│   ├── mtr_news.py
│   ├── wscn_news.py
│   └── x/                           # X/Twitter 子模块
│       ├── x_tweets.py
│       ├── x_accounts.json          # 账号列表（自动维护 user_id）
│       └── x_tweets_config.txt      # Cookie 配置（不入库）
├── all_sources_master.csv           # 总表（运行后生成）
└── history/                         # 分表快照（运行后生成）
    ├── all_sources_new_20260420_080000.csv
    ├── all_sources_new_20260420_090000.csv
    └── ...
```

## 输出说明

- **总表** `all_sources_master.csv`：累计所有新闻，每次运行追加新增条目
- **分表** `history/all_sources_new_YYYYMMDD_HHMMSS.csv`：每次抓取的新增部分单独存为一个快照，动态保留最近 12 次

## 统一字段

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识，格式 `{source}\|{primary_key}` |
| `source` | 数据源名称 |
| `url` | 原文链接（已去除追踪参数） |
| `headline` | 标题 |
| `abstract` | 摘要 |
| `img_url` | 封面图 |
| `publish_time` | 发布时间（统一 UTC+8 `YYYY-MM-DD HH:MM:SS`） |

## 去重机制

4 层精确匹配，任意一层命中即判为重复：

1. **id** — 源站原生 ID
2. **url** — 去追踪参数后精确匹配
3. **headline_day** — 标题小写 + 发布日期
4. **headline_abstract** — 标题小写 + 摘要前 160 字符

## 快速开始

```bash
# 安装依赖
pip install requests

# 抓取全部数据源
python3 main.py

# 仅抓取指定源
python3 main.py --sources hn_news,github_trending

# 调整翻页和并发
python3 main.py --max-pages 3 --page-size 30 --workers 8
```

## 命令行参数

### 通用参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--sources` | `all` | 数据源，支持 `all` 或逗号分隔的多个名称 |
| `--output` | `all_sources_master.csv` | 总表输出路径 |
| `--history-dir` | `history` | 分表快照目录 |
| `--history-limit` | `12` | 保留最近多少次分表快照 |
| `--max-pages` | `1` | 大多数分页源的最大翻页数 |
| `--page-size` | `20` | 大多数分页源的每页条数 |
| `--delay` | `0.5` | 翻页间隔秒数 |
| `--workers` | `6` | 并发线程数 |
| `--source-output-dir` | | 可选，按 source 输出单独 CSV 的目录 |

### GitHub Trending

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--github-since` | `daily` | 周期：`daily` / `weekly` / `monthly` |
| `--github-language` | | 按编程语言筛选 |

### X (Twitter)

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--x-auth-token` | | Cookie auth_token（或设环境变量 `X_AUTH_TOKEN`） |
| `--x-ct0` | | Cookie ct0（或设环境变量 `X_CT0`） |
| `--x-count` | `20` | 每个账号抓取条数 |
| `--x-max-pages` | `1` | 最大翻页数 |
| `--x-accounts` | | 账号列表，格式 `handle` 或 `handle:user_id` |

X 的凭证优先从环境变量 `X_AUTH_TOKEN` / `X_CT0` 读取，也可通过命令行传入，回退到 `sources/x/x_tweets_config.txt`。

## 新增数据源

1. 在 `sources/` 下新建脚本，实现抓取函数并返回 `list[dict]`
2. 在 `main.py` 中添加 `run_xxx` 调度函数
3. 在 `SOURCE_TASKS` 字典中注册新源
4. 如需特殊字段映射，在 `normalize_row` 中添加对应分支
