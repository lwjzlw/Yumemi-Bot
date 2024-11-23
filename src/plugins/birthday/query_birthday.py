import json
from datetime import datetime

def get_today_birthdays(file_path: str) -> str:
    """
    获取今天生日的人的名字
    :param file_path: JSON 文件路径
    :return: 今天生日的名字或提示信息
    """
    # 获取今天的日期（格式 MM-DD）
    today = datetime.now().strftime("%m-%d")

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
    if today_birthdays:
        return "今天生日的有：\n" + "\n".join(today_birthdays)
    else:
        return "今天没有人过生日。"