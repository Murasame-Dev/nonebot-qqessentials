from nonebot import on_command, on_message, get_plugin_config
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, MessageSegment
from nonebot.permission import SUPERUSER
from nonebot.log import logger
from .config import Config

# 创建配置实例
config = get_plugin_config(Config)

# 发送私聊消息功能
send_private_msg = on_command("发送私聊消息", priority=5, permission=SUPERUSER)

@send_private_msg.handle()
async def handle_send_private_msg(bot: Bot, event: MessageEvent):
    """发送私聊消息处理器"""
    # 获取命令参数
    message_text = str(event.get_message()).strip()
    
    # 提取参数（去掉命令前缀）
    args = ""
    if message_text.startswith("/发送私聊消息"):
        args = message_text[7:].strip()
    elif message_text.startswith("发送私聊消息"):
        args = message_text[6:].strip()
    
    if not args:
        await send_private_msg.send("请输入要发送的QQ号和消息内容\n格式：/发送私聊消息 QQ号 消息内容")
        return
    
    # 解析参数：QQ号 消息内容
    args_parts = args.split(maxsplit=1)
    if len(args_parts) < 2:
        await send_private_msg.send("❌ 参数不完整\n格式：/发送私聊消息 QQ号 消息内容\n例如：/发送私聊消息 123456789 你好")
        return
    
    try:
        user_id = int(args_parts[0])
        message_content = args_parts[1]
    except ValueError:
        await send_private_msg.send("❌ QQ号必须是数字\n格式：/发送私聊消息 QQ号 消息内容\n例如：/发送私聊消息 123456789 你好")
        return
    
    try:
        # 构造消息格式（NapCat需要的格式）
        message_data = [
            {
                "type": "text",
                "data": {
                    "text": message_content
                }
            }
        ]
        
        # 调用发送私聊消息接口
        result = await bot.call_api("send_private_msg", user_id=user_id, message=message_data)
        
        # 获取消息ID
        message_id = result.get('data', {}).get('message_id', 'N/A')
        
        await send_private_msg.send(f"✅ 私聊消息发送成功\n👤 接收者：{user_id}\n💬 内容：{message_content}\n🆔 消息ID：{message_id}")
        
    except Exception as e:
        logger.error(f"发送私聊消息失败: {e}")
        await send_private_msg.send(f"❌ 发送私聊消息失败：{str(e)}")

# 赞我功能 - 不需要指令头，不需要SUPERUSER权限
async def like_me_rule(event: MessageEvent) -> bool:
    """匹配"赞我"消息的规则"""
    message_text = str(event.get_message()).strip()
    return message_text == "赞我"

like_me = on_message(rule=like_me_rule, priority=5)

@like_me.handle()
async def handle_like_me(bot: Bot, event: MessageEvent):
    """处理赞我功能"""
    user_id = event.user_id
    logger.info(f"赞我功能被触发，用户：{user_id}")
    
    try:
        # 首先检查是否为QQ好友
        friend_list = await bot.get_friend_list()
        is_friend = any(friend['user_id'] == user_id for friend in friend_list)
        
        if not is_friend:
            await like_me.send("不加好友不赞😒")
            return
        
        # 调用点赞接口，使用配置的点赞次数
        await bot.call_api("send_like", user_id=user_id, times=config.default_like_times)
        
        # 成功的话输出已点赞消息
        await like_me.send(f"已赞了你{config.default_like_times}次哦！记得回我~")
        
        logger.info(f"点赞成功，用户：{user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"点赞失败: {error_msg}")
        
        # 判断是否是今天已经点过赞的错误
        if "已赞" in error_msg or "today" in error_msg.lower() or "today" in str(e).lower():
            await like_me.send("今天已经为你点过赞了")
        else:
            await like_me.send("今天已经为你点过赞了")  # 默认提示，因为大多数失败都是这个原因

# 删除好友功能
delete_friend_cmd = on_command("删除好友", priority=5, permission=SUPERUSER)

@delete_friend_cmd.handle()
async def handle_delete_friend(bot: Bot, event: MessageEvent):
    """删除好友处理器"""    # 检查功能是否启用
    if not config.enable_delete_friend:
        # 功能关闭时静默返回，不输出任何消息
        return
    
    # 获取完整消息内容
    message_text = str(event.get_message()).strip()
    
    # 提取参数（去掉命令前缀）
    args = ""
    if message_text.startswith("/删除好友"):
        args = message_text[5:].strip()  # 去掉"/删除好友"
    elif message_text.startswith("删除好友"):
        args = message_text[4:].strip()  # 去掉"删除好友"
    
    if not args:
        await delete_friend_cmd.send("请输入要删除的QQ号\n格式：/删除好友 QQ号")
        return
    
    # 解析QQ号
    try:
        user_id = int(args)
        logger.info(f"准备删除好友：{user_id}")
    except ValueError:
        await delete_friend_cmd.send("❌ QQ号必须是数字\n格式：/删除好友 QQ号\n例如：/删除好友 123456789")
        return
    
    try:
        # 调用删除好友接口
        await bot.call_api("delete_friend", user_id=user_id)
        await delete_friend_cmd.send(f"✅ 已删除好友：{user_id}")
        logger.info(f"删除好友成功：{user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"删除好友失败: {error_msg}")
        await delete_friend_cmd.send(f"❌ 删除好友失败：{error_msg}")
