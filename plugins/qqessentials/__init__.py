from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from . import __main__ as __main__
from . import friend as friend
from . import group as group


from .config import Config

__plugin_meta__ = PluginMetadata(
    name="QQEssentials",
    description="QQ机器人基础功能插件",
    usage="提供机器人信息查询、个性签名修改、头像修改、状态设置等功能",
    config=Config,
)

config = get_plugin_config(Config)
