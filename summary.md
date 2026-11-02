# hatstack 工作总结

> 会话时间：2026-11-01 ~ 11-02 ｜ 从"226 场 BlackHat PDF 下载脚本"到"11,500+ 场多会议安全档案搜索引擎"

---

## 一、交付物总览

| 交付物 | 地址 / 位置 | 状态 |
|---|---|---|
| **hatstack 搜索站** | https://xiaolichan.github.io/hatstack/ | 🟢 线上，11,573 场（补漏批落地后持续增长） |
| **个人主页** | https://xiaolichan.github.io/ | 🟢 线上，终端风 + 自打字动效 + 头像 |
| **GitHub Profile README** | github.com/XiaoliChan | 🟢 黑终端风，统计卡走 repo 内置文件（国内可载） |
| **爬虫框架** | `crawler/` ｜ 9 适配器 + 共享引擎 | 🟢 37 单测全绿，月度自动运行 |
| **数据** | `dataset/`（聚合 + 按会议拆分 + 按会议报告） | 🟢 随爬自动提交 |

---

## 二、数据现状

| 会议 | 场次 | 采集通道 |
|---|---|---|
| CCC（122 场会议含 FrOSCon） | 6,676 | 官方 JSON API `api.media.ccc.de` |
| DEF CON（30 届含十余村落） | 2,329 | `media.defcon.org` 静态 autoindex（curl 通道） |
| BlackHat（28 届 ok / 43 场次在补） | 1,763+ | Wayback≤2025 + live 兜底 + 2013-15 slug 解析 |
| USENIX Security（2015-2025） | 455 | 静态列表页（一年一请求） |
| x33fcon（9 年） | 181 | 静态 markdown 议程（MDwiki 的 .md 直取） |
| OffensiveCon（5 年） | 90 | 静态 speaker 页 |
| KCon（2022-24） | 79 | history.html 历届页（中文议题） |
| **合计（当前提交）** | **11,573** | 查询验证：wmi 0→4、sql injection 2→16+ |

**在途**：BlackHat 最后 43 个缺口场次拆三小批（15+15+13）并行补爬中——含 2013/2014 详情页时代（新 slug 解析器：从 `us-15-Gaddam-Securing-Your-Big-Data.html` 式链接直接解析讲者+标题）。

**已知缺口**：2000-2009 老路径（`bh-usa-97/` 家族）多无 Wayback 存档，需扩充候选 URL（盲重试无效）；RTV 独立站内容经 DEF CON 村落 track 进库（`.org` 域名已被抢注，真身 `.io`）。

---

## 三、架构（最终形态）

```
crawler/confs/<id>.py          # 每会议一适配器：ID/NAME/URL/DESCRIPTION + collect(ctx)
   ├─ 通道按成本优选：API > 静态curl > 静态列表 > Wayback > 渲染(Playwright) > live浏览器
   ├─ 共享：net.py(curl GET) render.py(渲染) wayback.py(id_原始字节+CDX+429退避)
   │         capture.py(fresh-browser/event + CF挑战 + XHR捕获) dataset.py parse.py
   └─ 产出 records 型缓存（预解析）或 raw 型缓存（晚解析）

CI（crawl.yml 矩阵）：
   setup(算会议清单) → crawl × N 并行(每会议一 job，缓存 artifact) 
   → assemble(合并全部缓存 → 单点构建提交，先 pull 后构建 + 推送重试环)

dataset/
   dataset.json                 # 站点单一数据源（conferences manifest + editions 索引 + sessions）
   by-conference/<conf>.json    # 按会议拆分（manifest+editions+该会议 sessions）
   report/summary.md + <conf>.md # 总览 + 按会议完整性报告

site/（Vite+React+TS+shadcn/ui+MiniSearch）
   左侧竖排筛选栏（会议组标题带简介+官网外链+计数；期次 {Region}-{Year} 单选；独立滚轮）
   手动页码翻页 ｜ 徽章 {Conference}-{Region}-{Year} ｜ 分隔符无关搜索（zero-day=zeroday，严格相邻）
   会议名/官网/简介全部来自 dataset manifest（前端零硬编码）
```

---

## 四、关键战役记录（问题 → 根因 → 修复）

| # | 问题 | 根因 | 修复 |
|---|---|---|---|
| 1 | curl/requests 直连 blackhat.com 全 403 | CF 按 TLS 指纹识别（非 IP） | live 走真 Chromium；静态站走子进程 curl |
| 2 | 同一浏览器第二次导航硬封 | CF 会话升级评分 | **fresh browser per event**（Phase 0 六轮探针结论） |
| 3 | 页面内自制 fetch/XHR 全死 | Transcend airgap.js 劫持 + 深层封锁 | 捕获**页面自己的** sessions.json XHR |
| 4 | Wayback 大面积"无存档" | 429 被静默吞成 miss | 指数退避 + 现在时间戳直取 + 日志带 HTTP 状态 |
| 5 | eu-2018 之死（退出码1无 traceback） | 输出缓冲吞日志 + 疑似 C 层崩溃 | `python -u` + `faulthandler` + 逐事件兜底 |
| 6 | 单会议运行抹掉其它会议数据 | 合并粒度错误 | 按事件/缓存级合并 + prior sessions 回填 |
| 7 | DC33 村落 91 链接 404 | 目录名钉死未跟随探测 | villages/villages and creators 双探测 |
| 8 | USENIX 43 机构混入讲者 | 仅英文大小写过滤 | 多语言机构正则重写 |
| 9 | records 型缓存带病永生 | 预解析缓存不随解析器更新 | 修复后重爬刷新缓存 |
| 10 | 黑客马拉松式 CI 串行慢 | 9 家挤一个 runner | **矩阵并行**（每会议一 job，实测 8 家 30 分钟内完成） |
| 11 | blackhat 单跑 3 小时撞顶 | Wayback 限流下单 IP 吞吐不足 | **区域批次并行**（us/eu/asia 三 runner 分食）+ 超时 300 分钟 |
| 12 | assemble 提交竞速 rebase 冲突 | 重放旧 dataset 提交 | 先 pull 后从缓存构建 + hard-reset 重试环 + **artifact 回收术**（crawl 成功数据从 artifact 捞回，三次实战验证） |
| 13 | 2013/2015 列表页无 PDF 直链 | 时代差异：链接详情页 | 从详情页 slug 解析讲者+标题（零额外请求） |
| 14 | media.defcon.org 拒 urllib3 | CDN TLS 指纹歧视 | 子进程 curl 通道（net.py） |

---

## 五、隐私处理（用户要求）

- 公开页面抹除：Guangzhou / Security Consultant / 雇主名 / 真名（William Wong → 统一 XiaoliChan）
- 两个个人 repo 历史**孤儿分支重写**（单 init commit，旧 commit 移出所有分支）
- 遗留：GitHub SHA 级残迹需删库重建才能物理抹除（token 缺 delete_repo）
- 规则入长期记忆：公开页面永不主动加雇主/地点/职位-雇主对

---

## 六、剩余路线图（todo: conf-expansion）

**优先**：⭐P1 DEF CON 村落核对（数据已随 defcon track 流入，待清点）｜⭐P3 Virus Bulletin（1991-，论文 PDF 库）｜CN 补完：MOSEC（CI 探测）+ 看雪 SDC（论坛解析器）

**常规**：⑧hack.lu ⑨Nullcon ⑩Troopers ⑪小会议批量×9 ⑫HITB ⑬BSides/ShmooCon/DerbyCon/recon.cx ｜ BlackHat 2000-2009 候选 URL 扩充 ｜ ⑭文案收尾

**月度自愈**：每月 3 日 UTC 06:00 自动全量重爬 + 增量提交（缓存提交进仓库，只补缺口）

---

## 七、本会话学到的可复用知识

- GitHub Pages 对改名后的旧 project-site 路径**不重定向**
- Legacy Pages 部署不随 force-push 自动触发（需手动 POST /pages/builds）
- GitHub 并发组一次只保留一个 pending——多批次并行必须 per-run 命名组
- `if: always()` 步骤在 **job 超时取消时不执行**（artifact 丢失）——批量要小于单 job 容量
- `gh run download` 捞 artifact 是 CI 提交竞速的标准救场
- MDwiki 站点的内容页是静态 .md（直取免渲染）；域名被抢注是"站点消失"的常见真相（RTV .org→.io）
