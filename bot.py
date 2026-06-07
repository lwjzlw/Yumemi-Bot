import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OnebotAdapter  # 避免重复命名

# 初始化 NoneBot
nonebot.init()

# 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(OnebotAdapter)

# 在这里加载插件
#nonebot.load_builtin_plugins("nonebot-plugin-apscheduler")  # 内置插件
nonebot.load_plugin("nonebot_plugin_apscheduler")
# nonebot.load_plugin("nonebot_plugin_orm")
# nonebot.load_plugin("nonebot_plugin_chatrecorder")
# nonebot.load_plugin("nonebot_plugin_datastore")
# nonebot.load_plugin("nonebot_plugin_skland")
# nonebot.load_plugin("nonebot_plugin_meme_stickers")
nonebot.load_plugins("src/plugins")

if __name__ == "__main__":
    nonebot.run()