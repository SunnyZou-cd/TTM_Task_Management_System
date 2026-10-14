# 配置 Supabase 云同步

真实登录、邮件投递、跨设备同步尚未使用你的服务验证。本地测试使用模拟服务；完成以下步骤后再进行真实验收。注册服务可能涉及服务费用，邮箱地址与登录后的任务/便笺将存储于你选择的 Supabase 项目。请先查看服务的配额与价格。

1. 在 [Supabase](https://supabase.com/dashboard) 注册并创建项目，选择合适的数据区域，妥善保存数据库密码。成功标志：项目显示为可用，SQL Editor 可以打开。
2. 在 SQL Editor 粘贴本项目 `supabase/schema.sql` 全部内容，执行。成功标志：执行成功，Table Editor 出现 `pinboard_items`；表已启用 RLS。不要关闭 RLS，也不要在客户端填写数据库密码。
3. 在 Authentication → Providers 确认 Email 登录开启；在 Email Templates 的 Magic Link 模板中加入 `{{ .Token }}`，让邮件显示数字验证码。应用使用邮件 OTP，不使用浏览器登录链接。成功标志：模板包含验证码变量并保存成功。参考 [邮件无密码登录官方文档](https://supabase.com/docs/guides/auth/auth-email-passwordless)。
4. 在项目连接信息/API Keys 中复制 Project URL 与 **publishable key**（旧项目可使用 anon key）。地址应为 `https://项目编号.supabase.co`。切勿复制 `secret` 或 `service_role` 密钥。成功标志：应用云端配置保存成功。公开密钥本身不代替权限控制，权限由 RLS 负责。
5. 在应用输入你的邮箱并主动点击发送验证码，然后填写邮件中的数字验证码。免费内置邮件服务可能限制收件人和发送频率；如遇限制，请按项目后台提示配置自己的 SMTP。成功标志：显示你的邮箱，同步状态为已同步。
6. 新建一条测试任务，在另一个 Windows 设备配置同一项目并登录同一账号，点击同步。成功标志：同一条任务出现；修改、完成和删除也能在两台设备同步。
7. 断开网络后修改任务，重启应用，再恢复网络并同步。成功标志：离线修改保留并上传；同步失败时明确显示尚未同步。上传成功但下载失败也不会误报完成。

本机游客条目与账号条目隔离；首次登录不会自动上传游客内容。退出登录可重新看到游客条目。切换 Supabase 项目会退出登录并隔离不同项目的账号缓存；悬浮位置与置顶条目仅保存在本机，不云同步。云端使用更新时间与设备 ID 决定整条记录冲突，删除保留墓碑；这不是逐字段或协作编辑合并，设备系统时间错误可能影响冲突选择。

安全验收：使用另一个账号登录后不得看到第一个账号的数据，匿名请求不得读取表。依据 [Supabase RLS 官方文档](https://supabase.com/docs/guides/database/postgres/row-level-security)。数据导出只包含当前账号可见条目，不包含公开密钥或登录令牌。
