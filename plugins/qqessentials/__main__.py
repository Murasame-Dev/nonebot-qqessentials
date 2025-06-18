from typing import Any, Dict, Optional
import asyncio
from nonebot import on_command, on_message, get_driver, get_plugin_config
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, MessageSegment, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import to_me, Rule
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from .config import Config

# 创建配置实例
config = get_plugin_config(Config)

# 1. 机器人信息查询
robot_info = on_command("机器人信息", aliases={"机器人状态", "bot信息"}, priority=5, permission=SUPERUSER)

@robot_info.handle()
async def handle_robot_info(bot: Bot, event: MessageEvent):
    """获取机器人基本信息"""
    try:
        # 获取登录信息
        login_info = await bot.get_login_info()
        
        # 获取状态信息
        status_info = await bot.get_status()
        
        # 获取版本信息
        version_info = await bot.get_version_info()
        
        # 格式化信息
        info_text = f"""🤖 机器人信息
━━━━━━━━━━━━━━━━
👤 账号信息：
  ├ QQ号：{login_info.get('user_id', 'N/A')}
  └ 昵称：{login_info.get('nickname', 'N/A')}

📊 状态信息：
  ├ 在线状态：{'在线' if status_info.get('online', False) else '离线'}
  └ 运行状态：{'正常' if status_info.get('good', False) else '异常'}

⚙️ 版本信息：
  ├ 应用名称：{version_info.get('app_name', 'N/A')}
  ├ 应用版本：{version_info.get('app_version', 'N/A')}
  └ 协议版本：{version_info.get('protocol_version', 'N/A')}
━━━━━━━━━━━━━━━━"""
        
        await robot_info.send(info_text)
        
    except Exception as e:
        logger.error(f"获取机器人信息失败: {e}")
        await robot_info.send(f"❌ 获取机器人信息失败：{str(e)}")


# 2. 修改个性签名
modify_signature = on_command("修改个性签名", priority=5, permission=SUPERUSER)

@modify_signature.handle()
async def handle_modify_signature(bot: Bot, event: MessageEvent, state: T_State):
    """修改个性签名处理器"""
    # 获取命令后的内容 - 修复参数解析
    message_text = str(event.get_message()).strip()
    
    # 提取参数（去掉命令前缀）
    args = ""
    if message_text.startswith("/修改个性签名"):
        args = message_text[7:].strip()
    elif message_text.startswith("修改个性签名"):
        args = message_text[6:].strip()
    
    if not args:
        await modify_signature.send("请输入要设置的个性签名内容\n格式：/修改个性签名 内容")
        return
    
    try:
        # 调用设置个性签名接口 - 修复参数名称
        result = await bot.call_api("set_self_longnick", longNick=args)
        await modify_signature.send(f"✅ 个性签名已修改为：\n{args}")
        
    except Exception as e:
        logger.error(f"修改个性签名失败: {e}")
        error_msg = str(e)
        if "longNick" in error_msg or "longnick" in error_msg.lower():
            await modify_signature.send(f"❌ 参数错误，可能是OneBot实现版本问题\n错误详情：{error_msg}")
        else:
            await modify_signature.send(f"❌ 修改个性签名失败：{error_msg}")


# 3. 修改头像功能
modify_avatar = on_command("修改头像", priority=5, permission=SUPERUSER)

# 存储等待上传头像的用户
waiting_avatar_users: Dict[int, bool] = {}

@modify_avatar.handle()
async def handle_modify_avatar(bot: Bot, event: MessageEvent, matcher: Matcher):
    """修改头像处理器"""
    user_id = event.user_id
    
    # 检查是否已经在等待状态
    if user_id in waiting_avatar_users:
        await modify_avatar.send("您已经在上传头像中，请完成当前操作或等待超时")
        return
    
    # 标记用户进入等待状态
    waiting_avatar_users[user_id] = True
    
    await modify_avatar.send(f"📸 请在 {config.avatar_upload_timeout} 秒内发送要设置的头像图片\n发送'取消上传'可取消操作")
    
    # 创建临时处理器等待图片
    from datetime import timedelta
    temp_handler = on_message(priority=1, temp=True, expire_time=timedelta(seconds=config.avatar_upload_timeout))
    
    @temp_handler.handle()
    async def handle_avatar_image(temp_bot: Bot, temp_event: MessageEvent, temp_matcher: Matcher):
        """处理头像图片"""
        # 只处理同一用户的消息
        if temp_event.user_id != user_id:
            return
        
        # 处理取消命令
        if temp_event.get_plaintext().strip() == "取消上传":
            if user_id in waiting_avatar_users:
                del waiting_avatar_users[user_id]
            await temp_matcher.send("❌ 头像上传已取消")
            await temp_matcher.finish()
        
        # 检查是否包含图片
        image_segments = [seg for seg in temp_event.message if seg.type == "image"]
        if not image_segments:
            await temp_matcher.send("请发送图片，或发送'取消上传'取消操作")
            return
        
        # 获取图片URL
        image_url = image_segments[0].data.get("url")
        if not image_url:
            if user_id in waiting_avatar_users:
                del waiting_avatar_users[user_id]
            await temp_matcher.send("❌ 无法获取图片URL")
            await temp_matcher.finish()
        
        try:
            # 调用修改头像API
            await temp_bot.call_api("set_qq_avatar", file=image_url)
            if user_id in waiting_avatar_users:
                del waiting_avatar_users[user_id]
            await temp_matcher.send("✅ 头像修改成功！")
        except Exception as e:
            if user_id in waiting_avatar_users:
                del waiting_avatar_users[user_id]
            error_msg = str(e)
            if "retcode" in error_msg:
                await temp_matcher.send("❌ 头像修改失败，可能是图片格式不支持或网络问题")
            else:
                await temp_matcher.send(f"❌ 头像修改失败：{error_msg}")
        
        await temp_matcher.finish()
    
    # 设置超时清理
    async def cleanup_timeout():
        await asyncio.sleep(config.avatar_upload_timeout)
        if user_id in waiting_avatar_users:
            del waiting_avatar_users[user_id]
    
    # 启动超时任务
    asyncio.create_task(cleanup_timeout())


# 4. 在线状态设置
status_setting = on_command("状态设置", priority=5, permission=SUPERUSER)

# 可用的在线状态 - 按分类组织
ONLINE_STATUS_MAP = {
    # 基础状态
    "1": ({"status": 10, "ext_status": 0, "battery_status": 0}, "我在线上"),
    "2": ({"status": 30, "ext_status": 0, "battery_status": 0}, "离开"),
    "3": ({"status": 40, "ext_status": 0, "battery_status": 0}, "隐身"),
    "4": ({"status": 50, "ext_status": 0, "battery_status": 0}, "忙碌"),
    "5": ({"status": 60, "ext_status": 0, "battery_status": 0}, "Q我吧"),
    "6": ({"status": 70, "ext_status": 0, "battery_status": 0}, "请勿打扰"),
    "50": ({"status": 10, "ext_status": 1000, "battery_status": 50}, "我的电量50%"),
    
    # 娱乐状态
    "7": ({"status": 10, "ext_status": 1028, "battery_status": 0}, "听歌中"),
    "8": ({"status": 10, "ext_status": 1027, "battery_status": 0}, "timi中"),
    "9": ({"status": 10, "ext_status": 1021, "battery_status": 0}, "追剧中"),
    
    # 学习工作状态
    "10": ({"status": 10, "ext_status": 1018, "battery_status": 0}, "学习中"),
    "11": ({"status": 10, "ext_status": 2012, "battery_status": 0}, "肝作业"),
    "12": ({"status": 10, "ext_status": 2023, "battery_status": 0}, "搬砖中"),
    "13": ({"status": 10, "ext_status": 1300, "battery_status": 0}, "摸鱼中"),
    
    # 生活状态
    "14": ({"status": 10, "ext_status": 1016, "battery_status": 0}, "睡觉中"),
    "15": ({"status": 10, "ext_status": 1032, "battery_status": 0}, "熬夜中"),
    "16": ({"status": 10, "ext_status": 2015, "battery_status": 0}, "去旅行"),
    "17": ({"status": 10, "ext_status": 2003, "battery_status": 0}, "出去浪"),
    
    # 情绪状态
    "18": ({"status": 10, "ext_status": 1051, "battery_status": 0}, "恋爱中"),
    "19": ({"status": 10, "ext_status": 2006, "battery_status": 0}, "爱你"),
    "20": ({"status": 10, "ext_status": 1401, "battery_status": 0}, "emo中"),
    "21": ({"status": 10, "ext_status": 1062, "battery_status": 0}, "我太难了"),
    "22": ({"status": 10, "ext_status": 2013, "battery_status": 0}, "我想开了"),
    "23": ({"status": 10, "ext_status": 1052, "battery_status": 0}, "我没事"),
    "24": ({"status": 10, "ext_status": 1061, "battery_status": 0}, "想静静"),
    
    # 特殊状态
    "25": ({"status": 10, "ext_status": 1058, "battery_status": 0}, "元气满满"),
    "26": ({"status": 10, "ext_status": 1056, "battery_status": 0}, "嗨到飞起"),
    "27": ({"status": 10, "ext_status": 1071, "battery_status": 0}, "好运锦鲤"),
    "28": ({"status": 10, "ext_status": 1070, "battery_status": 0}, "宝宝认证"),
    "29": ({"status": 10, "ext_status": 1060, "battery_status": 0}, "无聊中"),
    "30": ({"status": 10, "ext_status": 1059, "battery_status": 0}, "悠哉哉"),
    
    # 其他状态
    "31": ({"status": 10, "ext_status": 1011, "battery_status": 0}, "信号弱"),
    "32": ({"status": 10, "ext_status": 1030, "battery_status": 0}, "今日天气"),
    "33": ({"status": 10, "ext_status": 2019, "battery_status": 0}, "我crash了"),
    "34": ({"status": 10, "ext_status": 2014, "battery_status": 0}, "被掏空"),
    "35": ({"status": 10, "ext_status": 2001, "battery_status": 0}, "难得糊涂"),
    "36": ({"status": 10, "ext_status": 1063, "battery_status": 0}, "一言难尽"),
    "37": ({"status": 10, "ext_status": 2025, "battery_status": 0}, "一起元梦"),
    "38": ({"status": 10, "ext_status": 2026, "battery_status": 0}, "求星搭子"),
    "39": ({"status": 10, "ext_status": 2037, "battery_status": 0}, "春日限定"),
    "40": ({"status": 10, "ext_status": 1201, "battery_status": 0}, "水逆退散")
}

# 状态分类定义
STATUS_CATEGORIES = {
    "基础": {
        "keys": ["1", "2", "3", "4", "5", "6"],
        "icon": "📱",
        "desc": "基础状态"
    },
    "娱乐": {
        "keys": ["7", "8", "9"],
        "icon": "🎵",
        "desc": "娱乐状态"
    },
    "学习工作": {
        "keys": ["10", "11", "12", "13"],
        "icon": "📚",
        "desc": "学习工作"
    },
    "生活": {
        "keys": ["14", "15", "16", "17"],
        "icon": "🏠",
        "desc": "生活状态"
    },
    "情绪": {
        "keys": ["18", "19", "20", "21", "22", "23", "24"],
        "icon": "💝",
        "desc": "情绪状态"
    },
    "特殊": {
        "keys": ["25", "26", "27", "28", "29", "30"],
        "icon": "✨",
        "desc": "特殊状态"
    },
    "其他": {
        "keys": ["31", "32", "33", "34", "35", "36", "37", "38", "39", "40"],
        "icon": "🔧",
        "desc": "其他状态"
    },
    "电量": {
        "keys": ["50"],
        "icon": "🔋",
        "desc": "电量状态"
    }
}

# 状态名称到编号的映射
STATUS_NAME_TO_KEY = {
    # 基础状态
    "我在线上": "1",
    "离开": "2", 
    "隐身": "3",
    "忙碌": "4",
    "Q我吧": "5",
    "请勿打扰": "6",
    
    # 娱乐状态
    "听歌中": "7",
    "timi中": "8",
    "追剧中": "9",
    
    # 学习工作状态
    "学习中": "10",
    "肝作业": "11",
    "搬砖中": "12",
    "摸鱼中": "13",
    
    # 生活状态
    "睡觉中": "14",
    "熬夜中": "15",
    "去旅行": "16",
    "出去浪": "17",
    
    # 情绪状态
    "恋爱中": "18",
    "爱你": "19",
    "emo中": "20",
    "我太难了": "21",
    "我想开了": "22",
    "我没事": "23",
    "想静静": "24",
    
    # 特殊状态
    "元气满满": "25",
    "嗨到飞起": "26",
    "好运锦鲤": "27",
    "宝宝认证": "28",
    "无聊中": "29",
    "悠哉哉": "30",
    
    # 其他状态
    "信号弱": "31",
    "今日天气": "32",
    "我crash了": "33",
    "被掏空": "34",
    "难得糊涂": "35",
    "一言难尽": "36",
    "一起元梦": "37",
    "求星搭子": "38",
    "春日限定": "39",
    "水逆退散": "40",
    
    # 电量状态（默认）
    "我的电量50%": "50"
}

@status_setting.handle()
async def handle_status_setting(bot: Bot, event: MessageEvent):
    """处理状态设置"""
    # 获取命令参数 - 修复参数解析
    message_text = str(event.get_message()).strip()
    
    # 提取参数（去掉命令前缀）
    args = ""
    if message_text.startswith("/状态设置"):
        args = message_text[5:].strip()
    elif message_text.startswith("状态设置"):
        args = message_text[4:].strip()
    
    # 处理分类查询
    if args in STATUS_CATEGORIES:
        category = STATUS_CATEGORIES[args]
        
        # 特殊处理电量分类
        if args == "电量":
            status_list = f"{category['icon']} {category['desc']}：\n"
            status_list += "━━━━━━━━━━━━━━━━\n"
            status_list += "  💡 电量状态说明：\n"
            status_list += "  └ 可以显示自定义电量百分比\n\n"
            status_list += "  📋 使用方法：\n"
            status_list += "  ├ /状态设置 50 [电量] - 设置电量状态\n"
            status_list += "  └ 电量范围：1-100\n\n"
            status_list += "  🔋 示例命令：\n"
            status_list += "  ├ /状态设置 50 88 - 设置电量88%\n"
            status_list += "  ├ /状态设置 50 20 - 设置电量20%\n"
            status_list += "  └ /状态设置 50 100 - 设置电量100%\n"
            status_list += "━━━━━━━━━━━━━━━━\n"
            status_list += "💡 提示：不输入电量默认为50%"
        else:
            status_list = f"{category['icon']} {category['desc']}：\n"
            status_list += "━━━━━━━━━━━━━━━━\n"
            
            for key in category["keys"]:
                _, status_name = ONLINE_STATUS_MAP[key]
                status_list += f"  {key}. {status_name}\n"
            
            status_list += "━━━━━━━━━━━━━━━━\n"
            status_list += f"使用方法：/状态设置 数字\n"
            status_list += f"例如：/状态设置 {category['keys'][0]} ({ONLINE_STATUS_MAP[category['keys'][0]][1]})"
        
        await status_setting.send(status_list)
        return
    
    # 处理电量设置特殊语法：/状态设置 50 [电量值]
    args_parts = args.split()
    if len(args_parts) == 2 and args_parts[0] == "50":
        try:
            battery_level = int(args_parts[1])
            if 1 <= battery_level <= 100:
                # 设置自定义电量状态
                battery_params = {"status": 10, "ext_status": 1000, "battery_status": battery_level}
                await bot.call_api("set_online_status", **battery_params)
                await status_setting.send(f"🔋 电量状态已设置为：我的电量{battery_level}%")
                return
            else:
                await status_setting.send("❌ 电量值必须在1-100之间\n💡 使用方法：/状态设置 50 [电量]\n🔋 例如：/状态设置 50 88")
                return
        except ValueError:
            await status_setting.send("❌ 电量值必须为数字\n💡 使用方法：/状态设置 50 [电量]\n🔋 例如：/状态设置 50 88")
            return
    
    # 如果没有参数或参数不是分类，显示基础状态和分类导航
    if not args or args not in ONLINE_STATUS_MAP and args not in STATUS_CATEGORIES and args not in STATUS_NAME_TO_KEY:
        if args:
            # 如果输入了无效的状态码，显示错误信息
            await status_setting.send("❌ 无效的状态码、状态名称或分类\n💡 使用 /状态设置 查看基础状态\n🔍 或使用以下分类查询：\n📱 /状态设置 基础\n🎵 /状态设置 娱乐\n📚 /状态设置 学习工作\n🏠 /状态设置 生活\n💝 /状态设置 情绪\n✨ /状态设置 特殊\n🔧 /状态设置 其他\n🔋 /状态设置 电量\n\n📝 支持格式：\n  ├ /状态设置 1 (数字)\n  └ /状态设置 我在线上 (名称)")
            return
        
        # 显示基础状态（默认页面）
        basic_category = STATUS_CATEGORIES["基础"]
        status_list = f"🔧 在线状态设置\n"
        status_list += "━━━━━━━━━━━━━━━━\n"
        status_list += f"{basic_category['icon']} {basic_category['desc']}：\n"
        
        for key in basic_category["keys"]:
            _, status_name = ONLINE_STATUS_MAP[key]
            status_list += f"  {key}. {status_name}\n"
        
        status_list += "\n🔍 更多分类状态：\n"
        for cat_name, cat_info in STATUS_CATEGORIES.items():
            if cat_name != "基础":
                status_list += f"  {cat_info['icon']} /状态设置 {cat_name}\n"
        
        status_list += "━━━━━━━━━━━━━━━━\n"
        status_list += "使用方法：/状态设置 数字 或 /状态设置 状态名\n"
        status_list += "例如：/状态设置 1 或 /状态设置 我在线上"
        
        await status_setting.send(status_list)
        return
    
    # 检查是否是状态名称，转换为对应的编号
    if args in STATUS_NAME_TO_KEY:
        args = STATUS_NAME_TO_KEY[args]
    
    # 检查参数是否为有效的状态编号
    if args not in ONLINE_STATUS_MAP:
        await status_setting.send("❌ 无效的状态码或状态名称\n💡 使用 /状态设置 查看可用状态\n📝 支持格式：\n  ├ /状态设置 1 (数字)\n  └ /状态设置 我在线上 (名称)")
        return
    
    # 设置具体状态
    status_params, status_name = ONLINE_STATUS_MAP[args]
    
    try:
        # 调用设置在线状态接口 - 修复参数格式
        await bot.call_api("set_online_status", **status_params)
        await status_setting.send(f"✅ 在线状态已设置为：{status_name}")
        
    except Exception as e:
        logger.error(f"设置在线状态失败: {e}")
        await status_setting.send(f"❌ 设置在线状态失败：{str(e)}")


# 5. 消息撤回功能
delete_msg = on_command("撤回", aliases={"撤"}, priority=5, permission=SUPERUSER)

@delete_msg.handle()
async def handle_delete_msg(bot: Bot, event: MessageEvent):
    """处理消息撤回"""
    # 检查是否引用了消息
    reply_msg = None
    for segment in event.get_message():
        if segment.type == "reply":
            reply_msg = segment
            break
    
    # 如果没有引用消息，不执行任何操作（静默失败）
    if not reply_msg:
        return
    
    try:
        # 获取被引用消息的ID
        message_id = reply_msg.data.get("id")
        if not message_id:
            return
        
        # 调用撤回消息接口
        await bot.call_api("delete_msg", message_id=message_id)
        
        # 撤回成功后不发送任何消息（静默成功）
        
    except Exception as e:
        # 撤回失败也不输出任何消息（静默失败）
        logger.error(f"消息撤回失败: {e}")
        pass


# 6. 戳一戳功能
# 自定义规则：匹配"戳我"（不需要指令头）
async def poke_me_rule(event: MessageEvent) -> bool:
    message_text = str(event.get_message()).strip()
    return message_text == "戳我"

# 自定义规则：匹配"戳"开头的消息（不需要指令头）
async def poke_cmd_rule(event: MessageEvent) -> bool:
    # 获取纯文本内容
    plain_text = event.get_plaintext().strip()
    
    # 检查是否有@某人的消息段
    has_at = any(seg.type == "at" for seg in event.message)
    
    # 匹配各种"戳"的情况
    if plain_text == "戳":
        return True
    if plain_text.startswith("戳 "):
        return True
    if plain_text == "戳" and has_at:
        return True
    if plain_text.startswith("戳 ") and has_at:
        return True
    
    return False

poke_me = on_message(rule=poke_me_rule, priority=5)
poke_cmd = on_message(rule=poke_cmd_rule, priority=5)

@poke_me.handle()
async def handle_poke_me(bot: Bot, event: MessageEvent):
    """处理戳我功能 - 戳自己"""
    logger.info(f"戳我功能被触发，用户：{event.user_id}")
    try:
        # 判断是私聊还是群聊场景
        if isinstance(event, GroupMessageEvent):
            logger.info(f"群聊场景，群号：{event.group_id}")
            # 群聊场景：戳发送者
            await bot.call_api("send_poke", 
                             user_id=event.user_id, 
                             group_id=event.group_id, 
                             target_id=event.user_id)
        elif isinstance(event, PrivateMessageEvent):
            logger.info("私聊场景")
            # 私聊场景：戳对方
            await bot.call_api("send_poke", 
                             user_id=event.user_id, 
                             target_id=event.user_id)
        
        logger.info("戳一戳发送成功")
        
    except Exception as e:
        logger.error(f"戳一戳失败: {e}")
        # 失败也不发送错误消息，保持静默
        pass

@poke_cmd.handle()
async def handle_poke_cmd(bot: Bot, event: MessageEvent):
    """处理戳指令 - 可以戳指定用户或自己"""
    logger.info(f"戳指令被触发，用户：{event.user_id}")
    
    # 确定戳一戳的目标
    target_user_id = event.user_id  # 默认戳自己
    
    # 检查消息中是否有@某人
    at_segments = [seg for seg in event.message if seg.type == "at"]
    if at_segments:
        # 如果有@某人，戳被@的人
        target_user_id = int(at_segments[0].data.get("qq", event.user_id))
        logger.info(f"检测到@某人，戳指定用户：{target_user_id}")
    else:
        # 检查是否有数字参数
        plain_text = event.get_plaintext().strip()
        if plain_text.startswith("戳 "):
            args = plain_text[2:].strip()  # 去掉"戳 "
            if args:
                try:
                    # 如果有参数，尝试解析为QQ号
                    target_user_id = int(args)
                    logger.info(f"戳指定QQ号：{target_user_id}")
                except ValueError:
                    # 如果不是数字，则戳自己
                    logger.info(f"参数无效，戳自己：{target_user_id}")
        else:
            logger.info(f"无参数，戳自己：{target_user_id}")
    
    try:
        # 判断是私聊还是群聊场景
        if isinstance(event, GroupMessageEvent):
            logger.info(f"群聊场景，群号：{event.group_id}")
            # 群聊场景：戳指定用户
            await bot.call_api("send_poke", 
                             user_id=event.user_id, 
                             group_id=event.group_id, 
                             target_id=target_user_id)
        elif isinstance(event, PrivateMessageEvent):
            logger.info("私聊场景")
            # 私聊场景：戳指定用户（通常是对方）
            await bot.call_api("send_poke", 
                             user_id=event.user_id, 
                             target_id=target_user_id)
        
        logger.info("戳一戳发送成功")
        
    except Exception as e:
        logger.error(f"戳一戳失败: {e}")
        # 失败也不发送错误消息，保持静默
        pass


# 添加帮助命令
help_command = on_command("QQEss帮助", aliases={"qqess帮助"}, priority=10, permission=SUPERUSER)
help_msg_command = on_command("消息发送帮助", priority=10, permission=SUPERUSER)
help_group_command = on_command("群组管理帮助", priority=10, permission=SUPERUSER)
help_status_command = on_command("状态帮助", priority=10, permission=SUPERUSER)

@help_command.handle()
async def handle_help(bot: Bot, event: MessageEvent):
    """显示帮助信息主页"""
    help_text = """🤖 QQ机器人功能列表
━━━━━━━━━━━━━━━━
📋 基础功能：
  └ /机器人信息 - 查看机器人基本信息

✏️ 个人设置：
  ├ /修改个性签名 内容 - 修改个性签名
  ├ /修改头像 - 修改QQ头像
  └ /状态设置 [参数] - 设置在线状态

🗑️ 消息管理：
  └ /撤回 或 /撤 - 引用消息回复进行撤回

🎯 互动功能：
  ├ 戳我 - 戳自己（无需指令头）
  ├ 戳 - 戳自己（无需指令头）
  ├ 戳 QQ号 - 戳指定QQ号（无需指令头）
  ├ 戳@某人 - 戳@的用户（无需指令头）
  └ 赞我 - 点赞功能（无需指令头，需要是好友）

💬 消息发送：[展开请用: /消息发送帮助]
🏷️ 群组管理：[展开请用: /群组管理帮助]
🔧 状态设置：[展开请用: /状态帮助]
━━━━━━━━━━━━━━━━
⚠️ 注意：管理功能大部分仅限超级用户使用"""
    
    await help_command.send(help_text)

@help_msg_command.handle()
async def handle_help_msg(bot: Bot, event: MessageEvent):
    """显示消息发送功能帮助"""
    help_text = """💬 消息发送功能详细说明
━━━━━━━━━━━━━━━━
📤 发送功能：
  ├ /发送私聊消息 QQ号 内容 - 发送私聊消息
  ├ /发送群消息 群号 内容 - 发送群消息
  └ /删除好友 QQ号 - 删除指定QQ好友（需配置启用）

💡 使用说明：
  • 发送消息功能仅SUPERUSER可用
  • 删除好友功能默认关闭，需配置启用
  • 支持发送文本消息到指定私聊或群聊
━━━━━━━━━━━━━━━━
👈 返回主菜单：/QQEss帮助"""
    
    await help_msg_command.send(help_text)

@help_group_command.handle()
async def handle_help_group(bot: Bot, event: MessageEvent):
    """显示群组管理功能帮助"""
    help_text = """🏷️ 群组管理功能详细说明
━━━━━━━━━━━━━━━━
📝 加群管理：
  ├ 加群请求推送 - 向配置的目标群推送对应群的加群请求（需配置启用）
  ├ /同意加群请求 - 引用加群请求消息回复（群管理员可用）
  └ /拒绝加群请求 [理由] - 引用加群请求消息回复（群管理员可用）

👥 成员管理：
  ├ /踹 @用户|QQ号 [群号] - 踢出指定用户（SUPERUSER权限）
  ├ /禁言 @用户|QQ号 [群号] 时间 - 禁言指定用户（SUPERUSER权限）
  ├ /解禁 @用户|QQ号 [群号] - 解除禁言指定用户（SUPERUSER权限）
  ├ /全群禁言 - 开启全群禁言（SUPERUSER权限）
  └ /全群解禁 - 关闭全群禁言（SUPERUSER权限）

👑 权限管理：
  ├ /设置管理员 @用户|QQ号 [群号] - 设置群管理员（SUPERUSER权限）
  ├ /取消管理员 @用户|QQ号 [群号] - 取消群管理员（SUPERUSER权限）
  ├ /设置头衔 @用户|QQ号 头衔名 - 设置群头衔（SUPERUSER权限，需群主）
  └ /取消头衔 @用户|QQ号 - 取消群头衔（SUPERUSER权限，需群主）

🚪 群聊管理：
  └ /退群 群号 - 退出指定群聊（SUPERUSER权限）

� 使用说明：
  • 大部分功能仅SUPERUSER可用
  • 头衔设置需要机器人为群主
  • 支持@用户或直接输入QQ号
  • 私聊中使用需要提供群号参数
━━━━━━━━━━━━━━━━
👈 返回主菜单：/QQEss帮助"""

    await help_group_command.send(help_text)

@help_status_command.handle()
async def handle_help_status(bot: Bot, event: MessageEvent):
    """显示状态设置功能帮助"""
    help_text = """🔧 状态设置功能详细说明
━━━━━━━━━━━━━━━━
📋 基础用法：
  ├ /状态设置 - 查看基础状态
  ├ /状态设置 基础 - 基础状态
  ├ /状态设置 娱乐 - 娱乐状态
  ├ /状态设置 学习工作 - 学习工作状态  
  ├ /状态设置 生活 - 生活状态
  ├ /状态设置 情绪 - 情绪状态
  ├ /状态设置 特殊 - 特殊状态
  └ /状态设置 其他 - 其他状态

⚡ 高级用法：
  ├ /状态设置 电量 - 电量状态说明
  ├ /状态设置 50 [1-100] - 设置电量
  ├ /状态设置 数字 - 用编号设置状态
  └ /状态设置 状态名 - 用名称设置状态

💡 使用说明：
  • 支持40+种个性状态，分类查看更方便
  • 可按分类浏览或直接输入状态名
  • 支持设置电量状态（1-100）
  • 支持数字编号快速设置
━━━━━━━━━━━━━━━━
👈 返回主菜单：/QQEss帮助"""
    
    await help_status_command.send(help_text)
