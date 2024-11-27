# Yumemi-Bot

## 目前实现功能（主要为测试）：
1. \#echo: 返回参数
2. \#chat: 接收prompt作为参数，调用azure openai api，返回回复。只实现了单轮对话。（需要设置环境变量"OPENAI_ENDPOINT" "OPENAI_API_KEY"  "OPENAI_API_VERSION"）
3. \#今日运势：返回今天的key运势！
4. \#为保证生日的分组转发正常运行，请在环境变量"QQ_ID"和"QQ_NUMBER"下规定bot的ID和QQ号


## 部署流程：
1. 按照nonebot2官方文档的教程安装pipx和nb-cli（好像不用？）
2. 现在用NapCat登陆qq了，不知道稳定性如何。
3. 安装requirements.txt的依赖。

## TODO：
优化下代码，现在代码有点丑陋（尤其是和config相关的）

添加数据库以及图片


## 运行：
```
python bot.py
```