from pydantic import BaseModel
from typing import List


class Config(BaseModel):
    """Plugin Config Here"""
    
    # 头像上传超时时间（秒）
    avatar_upload_timeout: int = 30
    
    # 默认点赞次数，SVIP可考虑修改到20次
    default_like_times: int = 10
    
    # 删除好友功能开关（默认关闭，安全考虑）
    # 环境变量：ENABLE_DELETE_FRIEND
    enable_delete_friend: bool = False
    
    # 加群请求信息推送开关（默认关闭）
    # 环境变量：ENABLE_GROUP_REQUEST_NOTIFY
    enable_group_request_notify: bool = False
    
    # 加群请求推送目标群号列表（只有这些群的加群请求会推送到对应群）
    # 环境变量：GROUP_REQUEST_NOTIFY_TARGET（多个群号用逗号分隔，如：123456789,987654321）
    group_request_notify_target: List[int] = []
