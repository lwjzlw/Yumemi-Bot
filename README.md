# Yumemi-Bot

## 目前实现功能（主要为测试）：
1. \#echo: 返回参数
2. \#chat: 接收prompt作为参数，调用azure openai api，返回回复。只实现了单轮对话。
需要设置环境变量"OPENAI_ENDPOINT" "OPENAI_API_KEY"  "OPENAI_API_VERSION"

## 部署流程：
1. 按照nonebot2官方文档的教程安装pipx和nb-cli（好像不用？）
2. 下载并运行Lagrange.OneBot，登陆qq。端口设置为1270。
3. 安装requirements.txt的依赖。

## 运行：
```
python bot.py
```