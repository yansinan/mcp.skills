# sway/waybar/ncm 技能归类记录

## 第一轮 (2026-06-23)
扫描 7 个技能，识别 4 层（sway / waybar / mpv / NCM 应用），移动 16 个内容片段。

## 第二轮 (2026-06-24) — "系统级优先于具体需求"

### 原则
- sway 设置 > waybar 设置 > mpv 设置 > 具体需求 (ncm)
- ncm waybar 设置经验应归到 waybar 里（方式而非内容）
- 涉及 sway 避免重复进程的部分归 sway 技能
- 架构模式技能 (sway-music-client) 剔除实现代码，只留模式图 + cross-ref

### 具体执行

#### Phase 1: sway 级模式 → sway-daemon-persistence
新增"外部组件启动模式"节，统一收纳：
- SWAYSOCK stale env + waybar-launch.sh 模板
- sway exec_always 多行 bash -c 解析陷阱
- sway exec_always 不要用 pkill -f 匹配自身
- foot --float flag 不存在 + 加 -H 必加
- 启动方式选择表 (exec / exec_always / nohup / systemd)

应用层改为 cross-ref 的 skill：
- ncm-cli-setup (2 处)
- ncm-state-daemon (1 处)
- sway-music-client (1 处，30 行 → 2 行)
- mpv-waybar-control (3 个 pitfall 加 cross-ref 头注)
- mpv-mpris-media-stack (4 个 pitfall #11 #15 #17 #22)
- waybar-config (2 个 pitfall)

#### Phase 2: waybar 级 pitfall → waybar-config
新增 5 个通用 waybar pitfall：
- mpris interval 默认 5s 拦截 Playing 信号
- emoji 在 waybar 显示成方块
- Requested height warning
- pulseaudio format-icons 为空
- modules overflow on narrow portrait screens
- format-stopped 用 "" 而非 " "（W2 from waybar-integration-pitfalls.md）

#### Phase 3: sway-music-client 吸收 NCM 实现细节
- daemon bash 代码 (~80 行) → ncm-state-daemon "完整 daemon 循环实现"节
- waybar JSON 配置 + CSS 状态类 + 7 模块字段表 → ncm-cli-setup "waybar 集成"节
- 登录门控模块隐藏 + CSS 状态类路由 → ncm-cli-setup
- sway-music-client 保留: 架构决策 + 模式图 + cross-refs

#### 验证
- 18 条 cross-ref，100% 验证指向真实存在的节标题

#### 清理
- waybar-integration-pitfalls.md (55 行) → 吸收 W2 → 更新引用 → 删除

#### frontmatter 更新
- waybar-config description → "consolidated waybar pitfalls"
- ncm-state-daemon description → "完整 daemon 循环实现 + 登录流程坑点"
- ncm-cli-setup description → "waybar 集成(CSS状态类/登录门控/7模块表) + 性能优化 + 后端选型"
