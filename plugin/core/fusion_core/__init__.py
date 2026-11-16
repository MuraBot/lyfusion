"""fusion-core:lyfusion v5 的引擎。只用 Python 标准库。"""

VERSION = "5.0.0-rc.1.1"
SCHEMA = 2  # 状态格式版本:config.json、local.json、fusion.db 共用。aq.2 及更早没写版本号,当作 1。只有旧版本会读错的改动才加 1;只加带默认值的新字段不用加。
