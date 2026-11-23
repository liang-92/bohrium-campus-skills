### 异常：权限锁定（owner 口令 + 空 user 口令）

本目录 `paper.pdf` 设置了 owner 口令，但 user 口令为空。普通阅读器打开不会提示输入口令。
请尝试空口令解密并正常解析；在 `source` 中写明 `encrypted: true`、`decrypted: true`，
不要把可读文件判成 unreadable。
