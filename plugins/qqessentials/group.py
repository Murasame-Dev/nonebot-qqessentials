from nonebot import on_command, get_plugin_config, on_request
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, MessageSegment, GroupRequestEvent, GroupMessageEvent
from nonebot.permission import SUPERUSER
from nonebot.log import logger
from .config import Config

# 创建配置实例
config = get_plugin_config(Config)

# 权限检查函数
async def check_group_admin_permission(bot: Bot, event: MessageEvent) -> bool:
    """检查用户是否为群管理员或群主"""
    if not isinstance(event, GroupMessageEvent):
        return False
    
    try:
        # 获取群成员信息
        member_info = await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id)
        role = member_info.get('role', 'member')
        return role in ['admin', 'owner']
    except Exception as e:
        logger.error(f"检查群管理员权限失败: {e}")
        return False

# 1. 发送群消息功能
send_group_msg = on_command("发送群消息", priority=5, permission=SUPERUSER)

@send_group_msg.handle()
async def handle_send_group_msg(bot: Bot, event: MessageEvent):
    """发送群消息处理器"""
    # 获取完整消息内容
    message_text = str(event.get_message()).strip()
    
    # 提取参数（去掉命令前缀）
    args = ""
    if message_text.startswith("/发送群消息"):
        args = message_text[6:].strip()  # 去掉"/发送群消息"
    elif message_text.startswith("发送群消息"):
        args = message_text[5:].strip()  # 去掉"发送群消息"
    
    if not args:
        await send_group_msg.send("请输入群号和消息内容\n格式：/发送群消息 群号 消息内容")
        return
    
    # 解析参数：群号 消息内容
    args_parts = args.split(maxsplit=1)
    if len(args_parts) < 2:
        await send_group_msg.send("❌ 参数不完整\n格式：/发送群消息 群号 消息内容\n例如：/发送群消息 123456789 你好大家")
        return
    
    try:
        group_id = int(args_parts[0])
        message_content = args_parts[1]
        logger.info(f"准备发送群消息到群：{group_id}，内容：{message_content}")
    except ValueError:
        await send_group_msg.send("❌ 群号必须是数字\n格式：/发送群消息 群号 消息内容\n例如：/发送群消息 123456789 你好大家")
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
        
        # 调用发送群消息接口
        result = await bot.call_api("send_group_msg", group_id=group_id, message=message_data)
        
        # 获取消息ID
        message_id = result.get('data', {}).get('message_id', 'N/A')
        
        await send_group_msg.send(f"✅ 群消息发送成功\n🏷️ 群号：{group_id}\n💬 内容：{message_content}\n🆔 消息ID：{message_id}")
        logger.info(f"群消息发送成功，群号：{group_id}，消息ID：{message_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"发送群消息失败: {error_msg}")
        await send_group_msg.send(f"❌ 发送群消息失败：{error_msg}")


# 2. 加群请求信息推送功能（可配置开关）
group_request_handler = on_request(priority=10)

@group_request_handler.handle()
async def handle_group_request_notify(bot: Bot, event: GroupRequestEvent):
    """处理加群请求，向指定目标群发送请求信息"""
    # 检查功能是否启用
    if not config.enable_group_request_notify:
        return
    
    # 检查是否配置了目标群
    if not config.group_request_notify_target:
        logger.warning("不是配置文件内配置的群号，忽略")
        return
    
    # 只处理加群请求 (add 和 ignore.add)
    if event.request_type == "group" and event.sub_type in ["add", "ignore.add"]:
        group_id = event.group_id
        user_id = event.user_id
        flag = event.flag
        comment = getattr(event, 'comment', '') or ''
        
        # 构造加群请求信息
        request_info = f"""📝 加群请求信息
━━━━━━━━━━━━━━━━
👤 申请人：{user_id}
🏷️ 群号：{group_id}
🔑 Flag：{flag}"""
        
        if comment:
            request_info += f"\n💬 备注：{comment}"
        
        request_info += f"""
━━━━━━━━━━━━━━━━
💡 管理员可引用此消息回复：
   /同意加群请求 或 /拒绝加群请求 [理由]"""
        
        # 向所有配置的目标群发送加群请求信息
        for target_group in config.group_request_notify_target:
            try:
                await bot.send_group_msg(group_id=target_group, message=request_info)
                logger.info(f"已向目标群 {target_group} 推送加群请求信息，申请群：{group_id}，申请人：{user_id}，flag：{flag}")
            except Exception as e:
                logger.error(f"向目标群 {target_group} 推送加群请求信息失败: {e}")


# 3. 处理加群请求功能

# 3.1 同意加群请求功能
approve_group_request = on_command("同意加群请求", priority=5)

@approve_group_request.handle()
async def handle_approve_group_request(bot: Bot, event: MessageEvent):
    """同意加群请求处理器"""
    # 检查是否为目标群（支持多个目标群）
    if not isinstance(event, GroupMessageEvent) or event.group_id not in config.group_request_notify_target:
        return
    
    # 检查权限（管理员或SUPERUSER）
    is_admin = await check_group_admin_permission(bot, event)
    is_superuser = await SUPERUSER(bot, event)
    
    if not (is_admin or is_superuser):
        return  # 权限不足时不输出消息，直接返回
    
    # 检查是否引用了消息
    if not hasattr(event, 'reply') or not event.reply:
        return  # 没有引用消息时不处理
    
    # 获取被引用的消息
    reply_message = event.reply
    
    try:
        # 获取消息内容，尝试提取flag
        message_content = str(reply_message.message)
        
        # 优化的flag提取逻辑，支持我们推送的消息格式
        flag = None
        import re
        
        # 匹配 "🔑 Flag：xxxxxxx" 或 "flag: xxxxxxx" 格式
        flag_patterns = [
            r'🔑\s*Flag[：:]\s*([a-zA-Z0-9_-]+)',
            r'flag[：:\s]*([a-zA-Z0-9_-]+)', 
            r'Flag[：:\s]*([a-zA-Z0-9_-]+)'
        ]
        
        for pattern in flag_patterns:
            flag_match = re.search(pattern, message_content, re.IGNORECASE)
            if flag_match:
                flag = flag_match.group(1)
                break
        
        if not flag:
            return  # 无法提取flag时不处理
        
        # 调用同意加群请求接口
        await bot.call_api("set_group_add_request", flag=flag, approve=True)
        
        await approve_group_request.send("✅ 已同意加群请求")
        logger.info(f"同意加群请求成功，flag: {flag}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"同意加群请求失败: {error_msg}")
        await approve_group_request.send(f"❌ 同意加群请求失败：{error_msg}")


# 3.2 拒绝加群请求功能
reject_group_request = on_command("拒绝加群请求", priority=5)

@reject_group_request.handle()
async def handle_reject_group_request(bot: Bot, event: MessageEvent):
    """拒绝加群请求处理器"""
    # 检查是否为目标群（支持多个目标群）
    if not isinstance(event, GroupMessageEvent) or event.group_id not in config.group_request_notify_target:
        return
    
    # 检查权限（管理员或SUPERUSER）
    is_admin = await check_group_admin_permission(bot, event)
    is_superuser = await SUPERUSER(bot, event)
    
    if not (is_admin or is_superuser):
        return  # 权限不足时不输出消息，直接返回
    
    # 检查是否引用了消息
    if not hasattr(event, 'reply') or not event.reply:
        return  # 没有引用消息时不处理
    
    # 获取拒绝理由
    message_text = str(event.get_message()).strip()
    reason = ""
    if message_text.startswith("/拒绝加群请求"):
        reason = message_text[7:].strip()  # 去掉"/拒绝加群请求"
    elif message_text.startswith("拒绝加群请求"):
        reason = message_text[6:].strip()  # 去掉"拒绝加群请求"
    
    # 获取被引用的消息
    reply_message = event.reply
    
    try:
        # 获取消息内容，尝试提取flag
        message_content = str(reply_message.message)
        
        # 优化的flag提取逻辑，支持我们推送的消息格式
        flag = None
        import re
        
        # 匹配 "🔑 Flag：xxxxxxx" 或 "flag: xxxxxxx" 格式
        flag_patterns = [
            r'🔑\s*Flag[：:]\s*([a-zA-Z0-9_-]+)',
            r'flag[：:\s]*([a-zA-Z0-9_-]+)', 
            r'Flag[：:\s]*([a-zA-Z0-9_-]+)'
        ]
        
        for pattern in flag_patterns:
            flag_match = re.search(pattern, message_content, re.IGNORECASE)
            if flag_match:
                flag = flag_match.group(1)
                break
        
        if not flag:
            return  # 无法提取flag时不处理
        
        # 调用拒绝加群请求接口
        await bot.call_api("set_group_add_request", flag=flag, approve=False, reason=reason)
        
        if reason:
            await reject_group_request.send(f"✅ 已拒绝加群请求\n💬 拒绝理由：{reason}")
        else:
            await reject_group_request.send("✅ 已拒绝加群请求")
        
        logger.info(f"拒绝加群请求成功，flag: {flag}，理由: {reason}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"拒绝加群请求失败: {error_msg}")
        await reject_group_request.send(f"❌ 拒绝加群请求失败：{error_msg}")
