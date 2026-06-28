# sway sid 升级 → dpkg conffile 冲突处理

## 场景
Debian trixie → sid 升级 sway 时 dpkg 卡在 `/etc/sway/config` 替换询问。

## 升级流程

```bash
# 1. 加 sid 源
echo 'deb http://mirrors.tuna.tsinghua.edu.cn/debian sid main' | sudo tee /etc/apt/sources.list.d/sid.list
sudo apt update

# 2. 安装新 sway
sudo apt install -t sid sway -y
# 若返回 RC=100:
#   dpkg -s sway | grep Status
#   → 如果显示 "install ok unpacked"，说明 conffile 卡住

# 3. 修复半配置状态
sudo cp /etc/sway/config.dpkg-new /etc/sway/config
sudo rm /etc/sway/config.dpkg-new
sudo dpkg --configure -a
# 应输出 "Setting up sway (1.12-1) ... Installing new version of config file ..."

# 4. 验证
sway --version          # → sway version 1.12
dpkg -s sway | grep Version  # → Version: 1.12-1

# 5. 清理 sid 源
sudo rm /etc/apt/sources.list.d/sid.list
sudo apt update
sudo apt autoremove -y

# 6. 确认版本优先级
apt-cache policy sway
# 期望:
#   Installed: 1.12-1
#   Candidate: 1.12-1
#   Version table:
#  *** 1.12-1 100
#        100 /var/lib/dpkg/status
#     1.10.1-2 500
#        500 http://... debian trixie/main amd64 Packages
```

## dpkg 半配置修复核心原理

1. `config.dpkg-new` 是老版本 trixie 的配置（1.10.1 自带），被 sid 版（1.12）的 `dpkg-new` 覆盖。
2. 如果用户没改过 `/etc/sway/config`，安全的做法是用新 `config.dpkg-new` 替换旧 `config`。
3. `dpkg --configure -a` 触发配置完成 → status 从 `unpacked` 变 `installed`。

## 验证

```bash
dpkg -s sway | grep "Status\|Version"
# → Status: install ok installed
# → Version: 1.12-1
```
