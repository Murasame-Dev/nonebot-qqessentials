from nonebot import on_command, get_plugin_config, on_request, on_message
from nonebot.rule import to_me
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
        
        await send_group_msg.send(f"✅ 群消息发送成功\n🏷️ 群号：{group_id}\n💬 内容：{message_content}")
        logger.info(f"群消息发送成功，群号：{group_id}，消息ID：{message_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"发送群消息失败: {error_msg}")
        await send_group_msg.send(f"❌ 发送群消息失败：{error_msg}")


# 2. 加群请求信息推送功能（可配置开关）
group_request_handler = on_request(priority=10)

@group_request_handler.handle()
async def handle_group_request_notify(bot: Bot, event: GroupRequestEvent):
    """处理加群请求，向对应群发送请求信息"""
    # 检查功能是否启用
    if not config.enable_group_request_notify:
        return
    
    # 检查是否配置了目标群
    if not config.group_request_notify_target:
        logger.warning("加群请求推送功能已启用，但未配置目标群号")
        return
    
    # 只处理加群请求 (add 和 ignore.add)
    if event.request_type == "group" and event.sub_type in ["add", "ignore.add"]:
        group_id = event.group_id
        user_id = event.user_id
        flag = event.flag
        comment = getattr(event, 'comment', '') or ''
        
        # 检查当前申请群是否在配置的目标群列表中
        if group_id not in config.group_request_notify_target:
            logger.info(f"群 {group_id} 未在配置的目标群列表中，忽略加群请求推送")
            return
        
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
        
        # 向对应群发送加群请求信息（就是申请群本身）
        try:
            await bot.send_group_msg(group_id=group_id, message=request_info)
            logger.info(f"已向群 {group_id} 推送加群请求信息，申请人：{user_id}，flag：{flag}")
        except Exception as e:
            logger.error(f"向群 {group_id} 推送加群请求信息失败: {e}")


# 3. 处理加群请求功能

# 3.1 同意加群请求功能
approve_group_request = on_command("同意加群请求", priority=5)

@approve_group_request.handle()
async def handle_approve_group_request(bot: Bot, event: MessageEvent):
    """同意加群请求处理器"""
    # 检查是否为目标群
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
    # 检查是否为目标群
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


# 4. 踹/踢用户功能
kick_user = on_command("踹", aliases={"踢"}, priority=5, permission=SUPERUSER)

@kick_user.handle()
async def handle_kick_user(bot: Bot, event: MessageEvent):
    """踹/踢用户处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not isinstance(event, GroupMessageEvent):
        # 在私聊中，需要@用户或QQ号，以及群号
        if not has_at_user and len(parts) < 3:
            await kick_user.send("❌ 在私聊中使用此命令必须提供参数\n格式：/踹 @用户 群号 或 /踹 QQ号 群号\n例如：/踹 @某人 987654321 或 /踹 123456789 987654321")
            return
        elif has_at_user and len(parts) < 2:
            await kick_user.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/踹 @用户 群号\n例如：/踹 @某人 987654321")
            return
    else:
        # 在群聊中，需要@用户或QQ号
        if not has_at_user and len(parts) < 2:
            await kick_user.send("❌ 请提供要踢出的用户\n格式：/踹 @用户 [群号] 或 /踹 QQ号 [群号]\n例如：/踹 @某人 或 /踹 123456789")
            return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
        except (ValueError, IndexError):
            await kick_user.send("❌ 请@要踢出的用户或提供QQ号\n格式：/踹 @用户 [群号] 或 /踹 QQ号 [群号]\n例如：/踹 @某人 或 /踹 123456789")
            return
    
    # 获取目标群号
    target_group_id = None
    
    if isinstance(event, GroupMessageEvent):
        # 在群聊中，群号是可选的
        if has_at_user:
            # 如果使用了@用户，检查是否还有额外的数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if numeric_parts:
                target_group_id = int(numeric_parts[0])
            else:
                target_group_id = event.group_id  # 使用当前群
        else:
            # 如果没有使用@用户，第二个参数可能是群号
            if len(args_parts) >= 2 and args_parts[1].isdigit():
                target_group_id = int(args_parts[1])
            else:
                target_group_id = event.group_id  # 使用当前群
    else:
        # 在私聊中必须提供群号
        if has_at_user:
            # 如果使用了@用户，查找数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if not numeric_parts:
                await kick_user.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/踹 @用户 群号\n例如：/踹 @某人 987654321")
                return
            target_group_id = int(numeric_parts[0])
        else:
            # 如果没有使用@用户，第二个参数必须是群号
            if len(args_parts) < 2 or not args_parts[1].isdigit():
                await kick_user.send("❌ 在私聊中使用此命令必须提供群号\n格式：/踹 QQ号 群号\n例如：/踹 123456789 987654321")
                return
            target_group_id = int(args_parts[1])
    
    # 检查是否试图踢出自己
    if target_user_id == event.user_id:
        await kick_user.send("❌ 不能踢出自己")
        return
    
    # 检查是否试图踢出机器人
    bot_info = await bot.get_login_info()
    if target_user_id == bot_info.get('user_id'):
        await kick_user.send("❌ 不能踢出机器人自己")
        return
    
    try:
        # 调用踢出用户接口
        await bot.call_api("set_group_kick", group_id=target_group_id, user_id=target_user_id)
        
        # 根据消息类型显示不同的成功信息
        if isinstance(event, GroupMessageEvent) and target_group_id == event.group_id:
            await kick_user.send(f"✅ 已将用户 {target_user_id} 踢出当前群")
        else:
            await kick_user.send(f"✅ 已将用户 {target_user_id} 踢出群 {target_group_id}")
        
        logger.info(f"踢出用户成功，目标用户：{target_user_id}，目标群：{target_group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"踢出用户失败: {error_msg}")
        await kick_user.send(f"❌ 踢出用户失败：{error_msg}")


# 5. 禁言/塞口球功能
ban_user = on_command("禁言", aliases={"塞口球"}, priority=5, permission=SUPERUSER)

@ban_user.handle()
async def handle_ban_user(bot: Bot, event: MessageEvent):
    """禁言/塞口球用户处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not isinstance(event, GroupMessageEvent):
        # 在私聊中，需要@用户或QQ号，群号，时间
        if not has_at_user and len(parts) < 4:
            await ban_user.send("❌ 在私聊中使用此命令必须提供完整参数\n格式：/禁言 @用户 群号 时间 或 /禁言 QQ号 群号 时间\n例如：/禁言 @某人 987654321 300 或 /禁言 123456789 987654321 300")
            return
        elif has_at_user and len(parts) < 3:
            await ban_user.send("❌ 在私聊中使用@用户时必须提供群号和时间\n格式：/禁言 @用户 群号 时间\n例如：/禁言 @某人 987654321 300")
            return
    else:
        # 在群聊中，需要@用户或QQ号，时间
        if not has_at_user and len(parts) < 3:
            await ban_user.send("❌ 请提供要禁言的用户和时间\n格式：/禁言 @用户 时间 或 /禁言 QQ号 时间\n例如：/禁言 @某人 300 或 /禁言 123456789 300")
            return
        elif has_at_user and len(parts) < 2:
            await ban_user.send("❌ 请提供禁言时间\n格式：/禁言 @用户 时间\n例如：/禁言 @某人 300")
            return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
        except (ValueError, IndexError):
            await ban_user.send("❌ 请@要禁言的用户或提供QQ号\n格式：/禁言 @用户 [群号] 时间 或 /禁言 QQ号 [群号] 时间")
            return
    
    # 获取目标群号和禁言时间
    target_group_id = None
    ban_duration = None
    
    if isinstance(event, GroupMessageEvent):
        # 在群聊中，群号是可选的，时间是必需的
        if has_at_user:
            # 如果使用了@用户，第一个数字参数可能是群号或时间
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if len(numeric_parts) >= 2:
                # 有两个数字参数，第一个是群号，第二个是时间
                target_group_id = int(numeric_parts[0])
                ban_duration = int(numeric_parts[1])
            elif len(numeric_parts) == 1:
                # 只有一个数字参数，是时间
                target_group_id = event.group_id
                ban_duration = int(numeric_parts[0])
            else:
                await ban_user.send("❌ 请提供禁言时间（秒）\n例如：/禁言 @某人 300")
                return
        else:
            # 如果没有使用@用户，解析参数
            if len(args_parts) >= 3 and args_parts[1].isdigit() and args_parts[2].isdigit():
                # QQ号 群号 时间
                target_group_id = int(args_parts[1])
                ban_duration = int(args_parts[2])
            elif len(args_parts) >= 2 and args_parts[1].isdigit():
                # QQ号 时间
                target_group_id = event.group_id
                ban_duration = int(args_parts[1])
            else:
                await ban_user.send("❌ 参数格式错误\n格式：/禁言 QQ号 时间 或 /禁言 QQ号 群号 时间")
                return
    else:
        # 在私聊中必须提供群号和时间
        if has_at_user:
            # 如果使用了@用户，查找数字参数作为群号和时间
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if len(numeric_parts) < 2:
                await ban_user.send("❌ 在私聊中使用@用户时必须提供群号和时间\n格式：/禁言 @用户 群号 时间\n例如：/禁言 @某人 987654321 300")
                return
            target_group_id = int(numeric_parts[0])
            ban_duration = int(numeric_parts[1])
        else:
            # 如果没有使用@用户，第二个和第三个参数必须是群号和时间
            if len(args_parts) < 3 or not args_parts[1].isdigit() or not args_parts[2].isdigit():
                await ban_user.send("❌ 在私聊中使用此命令必须提供群号和时间\n格式：/禁言 QQ号 群号 时间\n例如：/禁言 123456789 987654321 300")
                return
            target_group_id = int(args_parts[1])
            ban_duration = int(args_parts[2])
    
    # 检查禁言时间是否合理（0-2592000秒，即0-30天）
    if ban_duration < 0 or ban_duration > 2592000:
        await ban_user.send("❌ 禁言时间必须在0-2592000秒之间（0-30天）\n💡 设置为0表示解除禁言")
        return
    
    # 检查是否试图禁言自己
    if target_user_id == event.user_id:
        await ban_user.send("❌ 不能禁言自己")
        return
    
    # 检查是否试图禁言机器人
    bot_info = await bot.get_login_info()
    if target_user_id == bot_info.get('user_id'):
        await ban_user.send("❌ 不能禁言机器人自己")
        return    
    try:
        # 调用禁言用户接口
        await bot.call_api("set_group_ban", group_id=target_group_id, user_id=target_user_id, duration=ban_duration)
        
        logger.info(f"禁言用户成功，目标用户：{target_user_id}，目标群：{target_group_id}，时长：{ban_duration}秒，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"禁言用户失败: {error_msg}")
        await ban_user.send(f"❌ 禁言用户失败：{error_msg}")


# 6. 解禁功能
unban_user = on_command("解禁", priority=5, permission=SUPERUSER)

@unban_user.handle()
async def handle_unban_user(bot: Bot, event: MessageEvent):
    """解禁用户处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not isinstance(event, GroupMessageEvent):
        # 在私聊中，需要@用户或QQ号，以及群号
        if not has_at_user and len(parts) < 3:
            await unban_user.send("❌ 在私聊中使用此命令必须提供参数\n格式：/解禁 @用户 群号 或 /解禁 QQ号 群号\n例如：/解禁 @某人 987654321 或 /解禁 123456789 987654321")
            return
        elif has_at_user and len(parts) < 2:
            await unban_user.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/解禁 @用户 群号\n例如：/解禁 @某人 987654321")
            return
    else:
        # 在群聊中，需要@用户或QQ号
        if not has_at_user and len(parts) < 2:
            await unban_user.send("❌ 请提供要解禁的用户\n格式：/解禁 @用户 [群号] 或 /解禁 QQ号 [群号]\n例如：/解禁 @某人 或 /解禁 123456789")
            return
        elif has_at_user and len(parts) < 1:
            await unban_user.send("❌ 请@要解禁的用户\n格式：/解禁 @用户 [群号]")
            return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
        except (ValueError, IndexError):
            await unban_user.send("❌ 请@要解禁的用户或提供QQ号\n格式：/解禁 @用户 [群号] 或 /解禁 QQ号 [群号]")
            return
    
    # 获取目标群号
    target_group_id = None
    
    if isinstance(event, GroupMessageEvent):
        # 在群聊中，群号是可选的
        if has_at_user:
            # 如果使用了@用户，检查是否还有额外的数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if numeric_parts:
                target_group_id = int(numeric_parts[0])
            else:
                target_group_id = event.group_id  # 使用当前群
        else:
            # 如果没有使用@用户，第二个参数可能是群号
            if len(args_parts) >= 2 and args_parts[1].isdigit():
                target_group_id = int(args_parts[1])
            else:
                target_group_id = event.group_id  # 使用当前群
    else:
        # 在私聊中必须提供群号
        if has_at_user:
            # 如果使用了@用户，查找数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if not numeric_parts:
                await unban_user.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/解禁 @用户 群号\n例如：/解禁 @某人 987654321")
                return
            target_group_id = int(numeric_parts[0])
        else:
            # 如果没有使用@用户，第二个参数必须是群号
            if len(args_parts) < 2 or not args_parts[1].isdigit():
                await unban_user.send("❌ 在私聊中使用此命令必须提供群号\n格式：/解禁 QQ号 群号\n例如：/解禁 123456789 987654321")
                return
            target_group_id = int(args_parts[1])
    
    # 检查是否试图解禁机器人
    bot_info = await bot.get_login_info()
    if target_user_id == bot_info.get('user_id'):
        await unban_user.send("❌ 机器人无需解禁")
        return    
    try:
        # 调用解禁用户接口（禁言时间设置为0）
        await bot.call_api("set_group_ban", group_id=target_group_id, user_id=target_user_id, duration=0)
        
        logger.info(f"解禁用户成功，目标用户：{target_user_id}，目标群：{target_group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"解禁用户失败: {error_msg}")
        await unban_user.send(f"❌ 解禁用户失败：{error_msg}")


# 7. 全群禁言功能
ban_all = on_command("全群禁言", aliases={"肃静"}, priority=5, permission=SUPERUSER)

@ban_all.handle()
async def handle_ban_all(bot: Bot, event: MessageEvent):
    """全群禁言处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 检查是否在群聊中
    if not isinstance(event, GroupMessageEvent):
        await ban_all.send("❌ 全群禁言只能在群聊中使用")
        return
    
    group_id = event.group_id
    
    try:
        # 调用全群禁言接口
        await bot.call_api("set_group_whole_ban", group_id=group_id, enable=True)
        
        logger.info(f"全群禁言成功，群号：{group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"全群禁言失败: {error_msg}")
        await ban_all.send(f"❌ 全群禁言失败：{error_msg}")


# 8. 全群解禁功能
unban_all = on_command("全群解禁", aliases={"大赦天下"}, priority=5, permission=SUPERUSER)

@unban_all.handle()
async def handle_unban_all(bot: Bot, event: MessageEvent):
    """全群解禁处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 检查是否在群聊中
    if not isinstance(event, GroupMessageEvent):
        await unban_all.send("❌ 全群解禁只能在群聊中使用")
        return
    
    group_id = event.group_id
    
    try:
        # 调用全群解禁接口
        await bot.call_api("set_group_whole_ban", group_id=group_id, enable=False)
        
        logger.info(f"全群解禁成功，群号：{group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"全群解禁失败: {error_msg}")
        await unban_all.send(f"❌ 全群解禁失败：{error_msg}")


# 9. 设置管理员功能
set_admin = on_command("设置管理员", priority=5, permission=SUPERUSER)

@set_admin.handle()
async def handle_set_admin(bot: Bot, event: MessageEvent):
    """设置管理员处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not isinstance(event, GroupMessageEvent):
        # 在私聊中，需要@用户或QQ号，以及群号
        if not has_at_user and len(parts) < 3:
            await set_admin.send("❌ 在私聊中使用此命令必须提供参数\n格式：/设置管理员 @用户 群号 或 /设置管理员 QQ号 群号\n例如：/设置管理员 @某人 987654321 或 /设置管理员 123456789 987654321")
            return
        elif has_at_user and len(parts) < 2:
            await set_admin.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/设置管理员 @用户 群号\n例如：/设置管理员 @某人 987654321")
            return
    else:
        # 在群聊中，需要@用户或QQ号
        if not has_at_user and len(parts) < 2:
            await set_admin.send("❌ 请提供要设置为管理员的用户\n格式：/设置管理员 @用户 或 /设置管理员 QQ号\n例如：/设置管理员 @某人 或 /设置管理员 123456789")
            return
        elif has_at_user and len(parts) < 1:
            await set_admin.send("❌ 请@要设置为管理员的用户\n格式：/设置管理员 @用户")
            return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
        except (ValueError, IndexError):
            await set_admin.send("❌ 请@要设置为管理员的用户或提供QQ号\n格式：/设置管理员 @用户 [群号] 或 /设置管理员 QQ号 [群号]")
            return
    
    # 获取目标群号
    target_group_id = None
    
    if isinstance(event, GroupMessageEvent):
        # 在群聊中，群号是可选的
        if has_at_user:
            # 如果使用了@用户，检查是否还有额外的数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if numeric_parts:
                target_group_id = int(numeric_parts[0])
            else:
                target_group_id = event.group_id  # 使用当前群
        else:
            # 如果没有使用@用户，第二个参数可能是群号
            if len(args_parts) >= 2 and args_parts[1].isdigit():
                target_group_id = int(args_parts[1])
            else:
                target_group_id = event.group_id  # 使用当前群
    else:
        # 在私聊中必须提供群号
        if has_at_user:
            # 如果使用了@用户，查找数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if not numeric_parts:
                await set_admin.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/设置管理员 @用户 群号\n例如：/设置管理员 @某人 987654321")
                return
            target_group_id = int(numeric_parts[0])
        else:
            # 如果没有使用@用户，第二个参数必须是群号
            if len(args_parts) < 2 or not args_parts[1].isdigit():
                await set_admin.send("❌ 在私聊中使用此命令必须提供群号\n格式：/设置管理员 QQ号 群号\n例如：/设置管理员 123456789 987654321")
                return
            target_group_id = int(args_parts[1])
    
    # 检查是否试图设置机器人为管理员
    bot_info = await bot.get_login_info()
    if target_user_id == bot_info.get('user_id'):
        await set_admin.send("❌ 不能设置机器人为管理员")
        return
    
    try:
        # 调用设置管理员接口
        await bot.call_api("set_group_admin", group_id=target_group_id, user_id=target_user_id, enable=True)
        
        logger.info(f"设置管理员成功，目标用户：{target_user_id}，目标群：{target_group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"设置管理员失败: {error_msg}")
        await set_admin.send(f"❌ 设置管理员失败：{error_msg}")


# 10. 取消管理员功能
unset_admin = on_command("取消管理员", priority=5, permission=SUPERUSER)

@unset_admin.handle()
async def handle_unset_admin(bot: Bot, event: MessageEvent):
    """取消管理员处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not isinstance(event, GroupMessageEvent):
        # 在私聊中，需要@用户或QQ号，以及群号
        if not has_at_user and len(parts) < 3:
            await unset_admin.send("❌ 在私聊中使用此命令必须提供参数\n格式：/取消管理员 @用户 群号 或 /取消管理员 QQ号 群号\n例如：/取消管理员 @某人 987654321 或 /取消管理员 123456789 987654321")
            return
        elif has_at_user and len(parts) < 2:
            await unset_admin.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/取消管理员 @用户 群号\n例如：/取消管理员 @某人 987654321")
            return
    else:
        # 在群聊中，需要@用户或QQ号
        if not has_at_user and len(parts) < 2:
            await unset_admin.send("❌ 请提供要取消管理员的用户\n格式：/取消管理员 @用户 或 /取消管理员 QQ号\n例如：/取消管理员 @某人 或 /取消管理员 123456789")
            return
        elif has_at_user and len(parts) < 1:
            await unset_admin.send("❌ 请@要取消管理员的用户\n格式：/取消管理员 @用户")
            return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
        except (ValueError, IndexError):
            await unset_admin.send("❌ 请@要取消管理员的用户或提供QQ号\n格式：/取消管理员 @用户 [群号] 或 /取消管理员 QQ号 [群号]")
            return
    
    # 获取目标群号
    target_group_id = None
    
    if isinstance(event, GroupMessageEvent):
        # 在群聊中，群号是可选的
        if has_at_user:
            # 如果使用了@用户，检查是否还有额外的数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if numeric_parts:
                target_group_id = int(numeric_parts[0])
            else:
                target_group_id = event.group_id  # 使用当前群
        else:
            # 如果没有使用@用户，第二个参数可能是群号
            if len(args_parts) >= 2 and args_parts[1].isdigit():
                target_group_id = int(args_parts[1])
            else:
                target_group_id = event.group_id  # 使用当前群
    else:
        # 在私聊中必须提供群号
        if has_at_user:
            # 如果使用了@用户，查找数字参数作为群号
            numeric_parts = [part for part in args_parts if part.isdigit()]
            if not numeric_parts:
                await unset_admin.send("❌ 在私聊中使用@用户时必须提供群号\n格式：/取消管理员 @用户 群号\n例如：/取消管理员 @某人 987654321")
                return
            target_group_id = int(numeric_parts[0])
        else:
            # 如果没有使用@用户，第二个参数必须是群号
            if len(args_parts) < 2 or not args_parts[1].isdigit():
                await unset_admin.send("❌ 在私聊中使用此命令必须提供群号\n格式：/取消管理员 QQ号 群号\n例如：/取消管理员 123456789 987654321")
                return
            target_group_id = int(args_parts[1])
    
    # 检查是否试图取消机器人的管理员
    bot_info = await bot.get_login_info()
    if target_user_id == bot_info.get('user_id'):
        await unset_admin.send("❌ 不能取消机器人的管理员权限")
        return    
    try:
        # 调用取消管理员接口
        await bot.call_api("set_group_admin", group_id=target_group_id, user_id=target_user_id, enable=False)
        
        logger.info(f"取消管理员成功，目标用户：{target_user_id}，目标群：{target_group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"取消管理员失败: {error_msg}")
        await unset_admin.send(f"❌ 取消管理员失败：{error_msg}")


# 11. 退群功能
leave_group = on_command("退群", priority=5, permission=SUPERUSER)

@leave_group.handle()
async def handle_leave_group(bot: Bot, event: MessageEvent):
    """退群处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 获取完整消息内容
    message_text = str(event.get_message()).strip()
    
    # 提取参数（保持命令前缀的处理）
    args = ""
    if message_text.startswith("/退群"):
        args = message_text[3:].strip()  # 去掉"/退群"
    elif message_text.startswith("退群"):
        args = message_text[2:].strip()  # 去掉"退群"
    
    if not args:
        await leave_group.send("请输入要退出的群号\n格式：/退群 群号\n例如：/退群 123456789")
        return
    
    # 解析群号
    try:
        group_id = int(args.strip())
        logger.info(f"准备退出群：{group_id}，操作者：{event.user_id}")
    except ValueError:
        await leave_group.send("❌ 群号必须是数字\n格式：/退群 群号\n例如：/退群 123456789")
        return
    
    # 检查是否试图退出当前群（如果在群聊中）
    if isinstance(event, GroupMessageEvent) and group_id == event.group_id:
        await leave_group.send(f"⚠️ 将要退出当前群 {group_id}，操作不可逆！")    
    try:
        # 调用退群接口
        await bot.call_api("set_group_leave", group_id=group_id)
        
        # 根据情况决定是否发送成功消息
        if isinstance(event, GroupMessageEvent) and group_id == event.group_id:
            # 在当前群退出当前群，不发送消息（因为机器人已经退出）
            pass
        else:
            # 在私聊中或退出其他群，发送成功消息
            await leave_group.send(f"✅ 已成功退出群 {group_id}")
        
        logger.info(f"退群成功，群号：{group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"退群失败: {error_msg}")
        await leave_group.send(f"❌ 退群失败：{error_msg}")


# 12. 设置头衔功能
set_special_title = on_command("设置头衔", priority=5, permission=SUPERUSER)

@set_special_title.handle()
async def handle_set_special_title(bot: Bot, event: MessageEvent):
    """设置头衔处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 检查是否在群聊中
    if not isinstance(event, GroupMessageEvent):
        await set_special_title.send("❌ 设置头衔只能在群聊中使用")
        return
    
    group_id = event.group_id
      # 检查机器人是否为群主
    try:
        bot_info = await bot.get_login_info()
        bot_user_id = bot_info.get('user_id')
        if not bot_user_id:
            logger.error("无法获取机器人用户ID")
            return
            
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=int(bot_user_id))
        bot_role = member_info.get('role', 'member')
        
        if bot_role != 'owner':
            # 机器人不是群主，静默处理
            logger.info(f"设置头衔失败：机器人不是群主，群号：{group_id}，操作者：{event.user_id}")
            return
    except Exception as e:
        logger.error(f"检查群主权限失败: {e}")
        return
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not has_at_user and len(parts) < 3:
        await set_special_title.send("❌ 请提供要设置头衔的用户和头衔名\n格式：/设置头衔 @用户 头衔名 或 /设置头衔 QQ号 头衔名\n例如：/设置头衔 @某人 荣誉成员 或 /设置头衔 123456789 荣誉成员")
        return
    elif has_at_user and len(parts) < 2:
        await set_special_title.send("❌ 请提供头衔名\n格式：/设置头衔 @用户 头衔名\n例如：/设置头衔 @某人 荣誉成员")
        return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    title_start_index = 0
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            title_start_index = 0  # @用户时头衔从第一个参数开始
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
            title_start_index = 1  # QQ号时头衔从第二个参数开始
        except (ValueError, IndexError):
            await set_special_title.send("❌ 请@要设置头衔的用户或提供QQ号\n格式：/设置头衔 @用户 头衔名 或 /设置头衔 QQ号 头衔名")
            return
    
    # 获取头衔名（可能包含空格）
    if title_start_index < len(args_parts):
        special_title = " ".join(args_parts[title_start_index:])
    else:
        await set_special_title.send("❌ 请提供头衔名\n例如：/设置头衔 @某人 荣誉成员")
        return
    
    # 检查头衔名长度（QQ群头衔限制）
    if len(special_title) > 6:
        await set_special_title.send("❌ 头衔名不能超过6个字符")
        return
      # 检查是否试图设置机器人的头衔
    if target_user_id == int(bot_user_id):
        await set_special_title.send("❌ 不能设置机器人的头衔")
        return
    
    try:
        # 调用设置头衔接口
        await bot.call_api("set_group_special_title", group_id=group_id, user_id=target_user_id, special_title=special_title)
        
        # 不发送成功消息，静默处理
        logger.info(f"设置头衔成功，目标用户：{target_user_id}，头衔：{special_title}，群号：{group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"设置头衔失败: {error_msg}")
        await set_special_title.send(f"❌ 设置头衔失败：{error_msg}")


# 13. 取消头衔功能
remove_special_title = on_command("取消头衔", priority=5, permission=SUPERUSER)

@remove_special_title.handle()
async def handle_remove_special_title(bot: Bot, event: MessageEvent):
    """取消头衔处理器"""
    # 只允许SUPERUSER使用（已在命令注册时限制权限）
    
    # 检查是否在群聊中
    if not isinstance(event, GroupMessageEvent):
        await remove_special_title.send("❌ 取消头衔只能在群聊中使用")
        return
    
    group_id = event.group_id
    
    # 检查机器人是否为群主
    try:
        bot_info = await bot.get_login_info()
        bot_user_id = bot_info.get('user_id')
        if not bot_user_id:
            logger.error("无法获取机器人用户ID")
            return
            
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=int(bot_user_id))
        bot_role = member_info.get('role', 'member')
        
        if bot_role != 'owner':
            # 机器人不是群主，静默处理
            logger.info(f"取消头衔失败：机器人不是群主，群号：{group_id}，操作者：{event.user_id}")
            return
    except Exception as e:
        logger.error(f"检查群主权限失败: {e}")
        return
    
    # 获取参数（直接从消息中提取，去掉命令部分）
    message_text = str(event.get_message()).strip()
    # 分割消息，第一部分是命令，后续是参数
    parts = message_text.split()
    
    # 检查是否有@用户
    has_at_user = any(segment.type == "at" for segment in event.get_message())
    
    # 基础参数验证
    if not has_at_user and len(parts) < 2:
        await remove_special_title.send("❌ 请提供要取消头衔的用户\n格式：/取消头衔 @用户 或 /取消头衔 QQ号\n例如：/取消头衔 @某人 或 /取消头衔 123456789")
        return
    elif has_at_user and len(parts) < 1:
        await remove_special_title.send("❌ 请@要取消头衔的用户\n格式：/取消头衔 @用户")
        return
    
    # 参数从第二个部分开始
    args_parts = parts[1:]
    
    # 获取目标QQ号（支持@用户或直接输入QQ号）
    target_user_id = None
    
    # 首先尝试从消息段中找到@用户
    for segment in event.get_message():
        if segment.type == "at":
            target_user_id = int(segment.data["qq"])
            break
    
    # 如果没有找到@用户，尝试从文本参数中解析
    if target_user_id is None:
        try:
            target_user_id = int(args_parts[0])
        except (ValueError, IndexError):
            await remove_special_title.send("❌ 请@要取消头衔的用户或提供QQ号\n格式：/取消头衔 @用户 或 /取消头衔 QQ号")
            return
      # 检查是否试图取消机器人的头衔
    if target_user_id == int(bot_user_id):
        await remove_special_title.send("❌ 不能取消机器人的头衔")
        return
    
    try:
        # 调用设置头衔接口，传入空字符串表示取消头衔
        await bot.call_api("set_group_special_title", group_id=group_id, user_id=target_user_id, special_title="")
        
        # 不发送成功消息，静默处理
        logger.info(f"取消头衔成功，目标用户：{target_user_id}，群号：{group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"取消头衔失败: {error_msg}")
        await remove_special_title.send(f"❌ 取消头衔失败：{error_msg}")


# 14. 设置精华消息功能
def exact_match_rule(*keywords):
    """精确匹配规则：只有消息完全等于关键词时才触发"""
    async def _rule(event: MessageEvent) -> bool:
        message_text = str(event.get_message()).strip()
        return message_text in keywords
    return _rule

set_essence = on_message(rule=exact_match_rule("设置精华消息", "设精"), priority=5, block=True)

@set_essence.handle()
async def handle_set_essence(bot: Bot, event: MessageEvent):
    """设置精华消息处理器"""
    # 检查权限（管理员、群主或SUPERUSER）
    if not isinstance(event, GroupMessageEvent):
        logger.warning(f"设置精华消息：不在群聊中，用户：{event.user_id}")
        return
    
    # 检查用户权限
    is_admin = await check_group_admin_permission(bot, event)
    is_superuser = await SUPERUSER(bot, event)
    
    if not (is_admin or is_superuser):
        logger.warning(f"设置精华消息：权限不足，用户：{event.user_id}，群号：{event.group_id}")
        return
    
    # 检查是否引用了消息
    if not hasattr(event, 'reply') or not event.reply:
        logger.info(f"设置精华消息：未引用消息，群号：{event.group_id}，操作者：{event.user_id}")
        return
    
    try:
        # 获取被引用消息的ID
        message_id = event.reply.message_id
        if not message_id:
            logger.error(f"设置精华消息失败：无法获取消息ID，群号：{event.group_id}，操作者：{event.user_id}")
            return
        
        # 调用设置精华消息接口
        await bot.call_api("set_essence_msg", message_id=message_id)
        
        # 成功时静默处理，不发送消息
        logger.info(f"设置精华消息成功，消息ID：{message_id}，群号：{event.group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"设置精华消息失败: {error_msg}，群号：{event.group_id}，操作者：{event.user_id}")
        # 错误时静默处理，不发送任何消息


# 15. 取消精华消息功能
delete_essence = on_message(rule=exact_match_rule("取消精华消息", "取精"), priority=5, block=True)

@delete_essence.handle()
async def handle_delete_essence(bot: Bot, event: MessageEvent):
    """取消精华消息处理器"""
    # 检查权限（管理员、群主或SUPERUSER）
    if not isinstance(event, GroupMessageEvent):
        logger.warning(f"取消精华消息：不在群聊中，用户：{event.user_id}")
        return
    
    # 检查用户权限
    is_admin = await check_group_admin_permission(bot, event)
    is_superuser = await SUPERUSER(bot, event)
    
    if not (is_admin or is_superuser):
        logger.warning(f"取消精华消息：权限不足，用户：{event.user_id}，群号：{event.group_id}")
        return
    
    # 检查是否引用了消息
    if not hasattr(event, 'reply') or not event.reply:
        logger.info(f"取消精华消息：未引用消息，群号：{event.group_id}，操作者：{event.user_id}")
        return
    
    try:
        # 获取被引用消息的ID
        message_id = event.reply.message_id
        if not message_id:
            logger.error(f"取消精华消息失败：无法获取消息ID，群号：{event.group_id}，操作者：{event.user_id}")
            return
        
        # 调用取消精华消息接口
        await bot.call_api("delete_essence_msg", message_id=message_id)
        
        # 成功时静默处理，不发送消息
        logger.info(f"取消精华消息成功，消息ID：{message_id}，群号：{event.group_id}，操作者：{event.user_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"取消精华消息失败: {error_msg}，群号：{event.group_id}，操作者：{event.user_id}")
        # 错误时静默处理，不发送任何消息
