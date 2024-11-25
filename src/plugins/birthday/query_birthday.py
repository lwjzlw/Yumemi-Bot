import json
from datetime import datetime
from typing import Tuple, List
def get_birthdays(file_path: str, month: int=0, day: int=0) -> List[str]:
    """
    获取指定日期生日的人的名字
    :param file_path: JSON 文件路径
    :param month: 月
    :param day: 日
    :return: 今天过生日的列表
    """
    # 获取今天的日期（格式 MM-DD）
    if 1 <= month <= 12 and 1 <= day <= 31:
        date = datetime(2024, month, day)
    else:
        date = datetime.now()
    today = date.strftime("%-m-%-d")
    
    try:
        # 读取 JSON 文件
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return "生日记录文件未找到。"
    except json.JSONDecodeError:
        return "JSON 文件格式错误。"

    # 搜索今天生日的人
    today_birthdays = []
    for date, records in data.items():
        if date == today:  # 检查日期是否匹配
            for record in records:
                today_birthdays.append(record.get("cha_name", "未知角色"))

    # 返回结果
    return today_birthdays